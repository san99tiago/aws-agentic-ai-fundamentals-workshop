"""
Foundation stack: shared, pre-provisioned building blocks for the workshop.

Participants create the *AI resources* themselves in the notebooks (Guardrail,
Knowledge Base, Gateway, Harness, Runtime). This stack pre-creates everything
that is slow or IAM-heavy so the 2-hour session stays focused on Agentic AI:

    - S3 bucket with the customer knowledge-base documents (private, SSL only)
    - S3 bucket for agent code artifacts (direct code deploy to AgentCore Runtime)
    - Mock Banking API: Amazon API Gateway (REST, AWS_IAM auth) + AWS Lambda
    - Least-privilege IAM roles for Knowledge Base, Gateway, Harness and Runtime
"""

import json
import shutil
from pathlib import Path

from aws_cdk import (
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
    aws_apigateway as apigw,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_logs as logs,
    aws_s3 as s3,
    aws_s3_deployment as s3_deploy,
)
from constructs import Construct

INFRA_DIR = Path(__file__).resolve().parents[1]
BUILD_DIR = INFRA_DIR / ".build"


class FoundationStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, app_config: dict, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self.app_config = app_config
        self.prefix = app_config["resource_prefix"]
        self.env_name = app_config["deployment_environment"]
        self.customer_dir = Path(app_config["customer_dir"])

        self.create_buckets()
        self.create_banking_api()
        self.create_knowledge_base_role()
        self.create_gateway_role()
        self.create_harness_role()
        self.create_runtime_role()
        self.create_outputs()

    # ------------------------------------------------------------------ S3
    def _private_bucket(self, logical_id: str, suffix: str) -> s3.Bucket:
        return s3.Bucket(
            self,
            logical_id,
            bucket_name=f"{self.prefix}-{suffix}-{self.account}-{self.env_name}",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            versioned=False,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

    def create_buckets(self):
        self.docs_bucket = self._private_bucket("KnowledgeBaseDocsBucket", "kb-docs")
        s3_deploy.BucketDeployment(
            self,
            "KnowledgeBaseDocsDeployment",
            sources=[s3_deploy.Source.asset(str(self.customer_dir / "knowledge-base"))],
            destination_bucket=self.docs_bucket,
            destination_key_prefix="knowledge-base/",
        )
        self.artifacts_bucket = self._private_bucket("AgentArtifactsBucket", "artifacts")

    # ------------------------------------------------------------ Banking API
    def _prepare_lambda_asset(self) -> str:
        """Bundle the Lambda handler with the customer's mock data (no Docker needed)."""
        target = BUILD_DIR / "banking_api"
        shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(INFRA_DIR / "lambda" / "banking_api", target)
        shutil.copy(self.customer_dir / "banking-api-data.json", target / "banking-api-data.json")
        return str(target)

    def create_banking_api(self):
        self.banking_lambda = lambda_.Function(
            self,
            "BankingApiFunction",
            function_name=f"{self.prefix}-banking-api-{self.env_name}",
            runtime=lambda_.Runtime.PYTHON_3_13,
            architecture=lambda_.Architecture.ARM_64,
            handler="index.handler",
            code=lambda_.Code.from_asset(self._prepare_lambda_asset()),
            timeout=Duration.seconds(10),
            memory_size=256,
            environment={
                "LOG_LEVEL": self.app_config.get("log_level", "INFO"),
                "AGENT_NAME": self.app_config["agent_name"],
            },
            log_group=logs.LogGroup(
                self,
                "BankingApiLogs",
                log_group_name=f"/aws/lambda/{self.prefix}-banking-api-{self.env_name}",
                retention=logs.RetentionDays.ONE_WEEK,
                removal_policy=RemovalPolicy.DESTROY,
            ),
        )

        self.api = apigw.RestApi(
            self,
            "BankingRestApi",
            rest_api_name=f"{self.prefix}-banking-api-{self.env_name}",
            description=f"Mock Banking API (FICTITIOUS) for {self.app_config['agent_name']} - AWS_IAM protected",
            endpoint_types=[apigw.EndpointType.REGIONAL],
            deploy_options=apigw.StageOptions(
                stage_name=self.env_name,
                throttling_rate_limit=20,
                throttling_burst_limit=40,
                metrics_enabled=True,
            ),
            default_method_options=apigw.MethodOptions(authorization_type=apigw.AuthorizationType.IAM),
            cloud_watch_role=False,
        )
        integration = apigw.LambdaIntegration(self.banking_lambda)
        # Documented responses are required so the exported OpenAPI can be turned into MCP tools
        responses = [
            apigw.MethodResponse(status_code=code, response_models={"application/json": apigw.Model.EMPTY_MODEL})
            for code in ("200", "400", "404")
        ]

        cdt_model = self.api.add_model(
            "CdtSimulationModel",
            content_type="application/json",
            model_name="CdtSimulationRequest",
            schema=apigw.JsonSchema(
                schema=apigw.JsonSchemaVersion.DRAFT4,
                type=apigw.JsonSchemaType.OBJECT,
                required=["amount", "term_days"],
                properties={
                    "amount": apigw.JsonSchema(type=apigw.JsonSchemaType.NUMBER, description="Monto a invertir en COP"),
                    "term_days": apigw.JsonSchema(
                        type=apigw.JsonSchemaType.INTEGER, description="Plazo en dias: 90, 180, 360 o 540"
                    ),
                },
            ),
        )
        loan_model = self.api.add_model(
            "LoanSimulationModel",
            content_type="application/json",
            model_name="LoanSimulationRequest",
            schema=apigw.JsonSchema(
                schema=apigw.JsonSchemaVersion.DRAFT4,
                type=apigw.JsonSchemaType.OBJECT,
                required=["amount", "months", "rate_ea"],
                properties={
                    "amount": apigw.JsonSchema(type=apigw.JsonSchemaType.NUMBER, description="Monto del credito en COP"),
                    "months": apigw.JsonSchema(type=apigw.JsonSchemaType.INTEGER, description="Plazo en meses"),
                    "rate_ea": apigw.JsonSchema(
                        type=apigw.JsonSchemaType.NUMBER, description="Tasa efectiva anual en porcentaje, ej 18.0"
                    ),
                },
            ),
        )
        body_validator = self.api.add_request_validator("BodyValidator", validate_request_body=True)

        customers = self.api.root.add_resource("customers").add_resource("{customer_id}")
        customers.add_resource("products").add_method(
            "GET",
            integration,
            operation_name="getCustomerProducts",
            method_responses=responses,
            request_parameters={"method.request.path.customer_id": True},
        )
        customers.add_resource("transactions").add_method(
            "GET",
            integration,
            operation_name="getCustomerTransactions",
            method_responses=responses,
            request_parameters={
                "method.request.path.customer_id": True,
                "method.request.querystring.limit": False,
            },
        )
        simulations = self.api.root.add_resource("simulations")
        simulations.add_resource("cdt").add_method(
            "POST",
            integration,
            operation_name="simulateCdt",
            method_responses=responses,
            request_models={"application/json": cdt_model},
            request_validator=body_validator,
        )
        simulations.add_resource("loan").add_method(
            "POST",
            integration,
            operation_name="simulateLoan",
            method_responses=responses,
            request_models={"application/json": loan_model},
            request_validator=body_validator,
        )
        self.api.root.add_resource("exchange-rates").add_method(
            "GET", integration, operation_name="getExchangeRates", method_responses=responses
        )

    # ------------------------------------------------------------- IAM roles
    def _agentcore_trust(self, *resource_types: str) -> iam.PrincipalBase:
        """Trust bedrock-agentcore only for OUR account and resource types (confused-deputy protection)."""
        return iam.ServicePrincipal(
            "bedrock-agentcore.amazonaws.com",
            conditions={
                "StringEquals": {"aws:SourceAccount": self.account},
                "ArnLike": {
                    "aws:SourceArn": [
                        f"arn:aws:bedrock-agentcore:{self.region}:{self.account}:{resource_type}/*"
                        for resource_type in resource_types
                    ]
                },
            },
        )

    def _bedrock_invoke_statement(self) -> iam.PolicyStatement:
        return iam.PolicyStatement(
            sid="BedrockModelInvocation",
            actions=[
                "bedrock:InvokeModel",
                "bedrock:InvokeModelWithResponseStream",
                "bedrock:ApplyGuardrail",
            ],
            resources=[
                "arn:aws:bedrock:*::foundation-model/*",
                f"arn:aws:bedrock:*:{self.account}:inference-profile/*",
                f"arn:aws:bedrock:{self.region}:{self.account}:guardrail/*",
                f"arn:aws:bedrock:*:{self.account}:guardrail-profile/*",
            ],
        )

    def _observability_statements(self) -> list:
        log_group_arn = f"arn:aws:logs:{self.region}:{self.account}:log-group:/aws/bedrock-agentcore/runtimes/*"
        return [
            iam.PolicyStatement(
                sid="Logs",
                actions=["logs:CreateLogGroup", "logs:DescribeLogStreams", "logs:CreateLogStream", "logs:PutLogEvents"],
                resources=[log_group_arn, f"{log_group_arn}:log-stream:*"],
            ),
            iam.PolicyStatement(
                sid="LogsDescribe",
                actions=["logs:DescribeLogGroups"],
                resources=[f"arn:aws:logs:{self.region}:{self.account}:log-group:*"],
            ),
            iam.PolicyStatement(
                sid="XRay",
                actions=[
                    "xray:PutTraceSegments",
                    "xray:PutTelemetryRecords",
                    "xray:GetSamplingRules",
                    "xray:GetSamplingTargets",
                ],
                resources=["*"],
            ),
            iam.PolicyStatement(
                sid="Metrics",
                actions=["cloudwatch:PutMetricData"],
                resources=["*"],
                conditions={"StringEquals": {"cloudwatch:namespace": "bedrock-agentcore"}},
            ),
        ]

    def _invoke_gateway_statement(self) -> iam.PolicyStatement:
        return iam.PolicyStatement(
            sid="InvokeWorkshopGateways",
            actions=["bedrock-agentcore:InvokeGateway"],
            resources=[f"arn:aws:bedrock-agentcore:{self.region}:{self.account}:gateway/{self.prefix}*"],
        )

    def create_knowledge_base_role(self):
        self.kb_role = iam.Role(
            self,
            "KnowledgeBaseRole",
            role_name=f"{self.prefix}-kb-role-{self.env_name}",
            description="Amazon Bedrock Managed Knowledge Base service role (workshop)",
            assumed_by=iam.ServicePrincipal(
                "bedrock.amazonaws.com",
                conditions={
                    "StringEquals": {"aws:SourceAccount": self.account},
                    "ArnLike": {
                        "aws:SourceArn": f"arn:aws:bedrock:{self.region}:{self.account}:knowledge-base/*"
                    },
                },
            ),
        )
        self.docs_bucket.grant_read(self.kb_role)
        self.kb_role.add_to_policy(
            iam.PolicyStatement(
                sid="EmbeddingAndParsingModels",
                actions=["bedrock:InvokeModel"],
                resources=[
                    f"arn:aws:bedrock:{self.region}::foundation-model/amazon.titan-embed-text-v2:0",
                    "arn:aws:bedrock:*::foundation-model/*",
                ],
            )
        )

    def create_gateway_role(self):
        self.gateway_role = iam.Role(
            self,
            "GatewayRole",
            role_name=f"{self.prefix}-gateway-role-{self.env_name}",
            description="AgentCore Gateway service role: Web Search, Banking API and Knowledge Base targets",
            assumed_by=self._agentcore_trust("gateway"),
        )
        self.gateway_role.add_to_policy(self._invoke_gateway_statement())
        self.gateway_role.add_to_policy(
            iam.PolicyStatement(
                sid="InvokeWebSearch",
                actions=["bedrock-agentcore:InvokeWebSearch"],
                resources=[f"arn:aws:bedrock-agentcore:{self.region}:aws:tool/web-search.v1"],
            )
        )
        self.gateway_role.add_to_policy(
            iam.PolicyStatement(
                sid="InvokeBankingApi",
                actions=["execute-api:Invoke"],
                resources=[self.api.arn_for_execute_api(stage=self.env_name)],
            )
        )
        self.gateway_role.add_to_policy(
            iam.PolicyStatement(
                sid="ReadBankingApiDefinition",
                actions=["apigateway:GET"],
                resources=[
                    f"arn:aws:apigateway:{self.region}::/restapis/{self.api.rest_api_id}",
                    f"arn:aws:apigateway:{self.region}::/restapis/{self.api.rest_api_id}/*",
                ],
            )
        )
        self.gateway_role.add_to_policy(
            iam.PolicyStatement(
                sid="ManagedKnowledgeBase",
                actions=["bedrock:GetKnowledgeBase", "bedrock:Retrieve"],
                resources=[f"arn:aws:bedrock:{self.region}:{self.account}:knowledge-base/*"],
            )
        )
        self.gateway_role.add_to_policy(
            iam.PolicyStatement(
                sid="AgenticRetrieve", actions=["bedrock:AgenticRetrieveStream"], resources=["*"]
            )
        )

    def create_harness_role(self):
        self.harness_role = iam.Role(
            self,
            "HarnessRole",
            role_name=f"{self.prefix}-harness-role-{self.env_name}",
            description="AgentCore Harness execution role (workshop)",
            # A harness runs on an AgentCore Runtime it manages, so both ARNs assume the role
            assumed_by=self._agentcore_trust("harness", "runtime"),
        )
        for statement in [self._bedrock_invoke_statement(), self._invoke_gateway_statement(), *self._observability_statements()]:
            self.harness_role.add_to_policy(statement)
        self.harness_role.add_to_policy(
            iam.PolicyStatement(
                sid="EcrPublicPull",
                actions=["ecr-public:GetAuthorizationToken", "sts:GetServiceBearerToken"],
                resources=["*"],
            )
        )
        self.harness_role.add_to_policy(
            iam.PolicyStatement(
                sid="LogsResourcePolicy", actions=["logs:PutResourcePolicy"], resources=["*"]
            )
        )
        self.harness_role.add_to_policy(
            iam.PolicyStatement(
                sid="WorkloadIdentity",
                actions=["bedrock-agentcore:GetWorkloadAccessToken", "bedrock-agentcore:GetWorkloadAccessTokenForJWT"],
                resources=[
                    f"arn:aws:bedrock-agentcore:{self.region}:{self.account}:workload-identity-directory/default",
                    f"arn:aws:bedrock-agentcore:{self.region}:{self.account}:workload-identity-directory/default/workload-identity/*",
                ],
            )
        )
        self.harness_role.add_to_policy(
            iam.PolicyStatement(
                sid="CodeInterpreterAndBrowser",
                actions=[
                    "bedrock-agentcore:StartCodeInterpreterSession",
                    "bedrock-agentcore:StopCodeInterpreterSession",
                    "bedrock-agentcore:GetCodeInterpreterSession",
                    "bedrock-agentcore:ListCodeInterpreterSessions",
                    "bedrock-agentcore:InvokeCodeInterpreter",
                    "bedrock-agentcore:StartBrowserSession",
                    "bedrock-agentcore:StopBrowserSession",
                    "bedrock-agentcore:GetBrowserSession",
                    "bedrock-agentcore:ListBrowserSessions",
                    "bedrock-agentcore:UpdateBrowserStream",
                    "bedrock-agentcore:ConnectBrowserAutomationStream",
                    "bedrock-agentcore:ConnectBrowserLiveViewStream",
                ],
                resources=[
                    f"arn:aws:bedrock-agentcore:{self.region}:aws:code-interpreter/*",
                    f"arn:aws:bedrock-agentcore:{self.region}:aws:browser/*",
                ],
            )
        )
        self.harness_role.add_to_policy(
            iam.PolicyStatement(
                sid="ManagedMemory",
                actions=[
                    "bedrock-agentcore:CreateEvent",
                    "bedrock-agentcore:DeleteEvent",
                    "bedrock-agentcore:GetEvent",
                    "bedrock-agentcore:ListEvents",
                    "bedrock-agentcore:RetrieveMemoryRecords",
                ],
                resources=[f"arn:aws:bedrock-agentcore:{self.region}:{self.account}:memory/*"],
            )
        )

    def create_runtime_role(self):
        self.runtime_role = iam.Role(
            self,
            "RuntimeRole",
            role_name=f"{self.prefix}-runtime-role-{self.env_name}",
            description="AgentCore Runtime execution role for the Strands agent (workshop)",
            assumed_by=self._agentcore_trust("runtime"),
        )
        for statement in [self._bedrock_invoke_statement(), self._invoke_gateway_statement(), *self._observability_statements()]:
            self.runtime_role.add_to_policy(statement)
        self.artifacts_bucket.grant_read(self.runtime_role)
        self.runtime_role.add_to_policy(
            iam.PolicyStatement(
                sid="WorkloadIdentity",
                actions=["bedrock-agentcore:GetWorkloadAccessToken", "bedrock-agentcore:GetWorkloadAccessTokenForJWT"],
                resources=[
                    f"arn:aws:bedrock-agentcore:{self.region}:{self.account}:workload-identity-directory/default",
                    f"arn:aws:bedrock-agentcore:{self.region}:{self.account}:workload-identity-directory/default/workload-identity/*",
                ],
            )
        )

    # ------------------------------------------------------------- Outputs
    def create_outputs(self):
        outputs = {
            "KnowledgeBaseDocsBucketName": self.docs_bucket.bucket_name,
            "AgentArtifactsBucketName": self.artifacts_bucket.bucket_name,
            "BankingApiId": self.api.rest_api_id,
            "BankingApiStage": self.env_name,
            "BankingApiUrl": self.api.url,
            "KnowledgeBaseRoleArn": self.kb_role.role_arn,
            "GatewayRoleArn": self.gateway_role.role_arn,
            "HarnessRoleArn": self.harness_role.role_arn,
            "RuntimeRoleArn": self.runtime_role.role_arn,
            "ResourcePrefix": self.prefix,
        }
        for key, value in outputs.items():
            CfnOutput(self, key, value=value, export_name=f"{self.prefix}-{self.env_name}-{key}")
        CfnOutput(
            self,
            "WorkshopParams",
            value=json.dumps(
                {
                    "customer_id": self.app_config["customer_id"],
                    "customer_name": self.app_config["customer_name"],
                    "agent_name": self.app_config["agent_name"],
                }
            ),
        )
