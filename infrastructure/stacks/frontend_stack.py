"""
Frontend stack: workshop portal hosted on a PRIVATE S3 bucket behind Amazon
CloudFront (Origin Access Control). No S3 website hosting, no custom DNS: the
portal is served on the default *.cloudfront.net domain.

The portal is fully parametrized at runtime through /config.json, generated
here from the same cdk.json + .env parameters (no frontend rebuild needed per
customer).
"""

from pathlib import Path

from aws_cdk import (
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_s3 as s3,
    aws_s3_deployment as s3_deploy,
)
from constructs import Construct

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"

PUBLIC_CONFIG_KEYS = [
    "customer_id",
    "customer_name",
    "customer_brand",
    "agent_name",
    "agent_emoji",
    "primary_color",
    "secondary_color",
    "accent_color",
    "workshop_title",
    "workshop_date",
    "facilitator_name",
    "repo_url",
    "aws_region",
    "default_model_id",
    "fast_model_id",
    "top_model_id",
]


class FrontendStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, app_config: dict, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self.app_config = app_config
        prefix = app_config["resource_prefix"]
        env_name = app_config["deployment_environment"]

        if not (FRONTEND_DIST / "index.html").exists():
            raise FileNotFoundError(
                f"{FRONTEND_DIST}/index.html not found. Build the portal first: cd frontend && npm ci && npm run build"
            )

        bucket = s3.Bucket(
            self,
            "PortalBucket",
            bucket_name=f"{prefix}-portal-{self.account}-{env_name}",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        security_headers = cloudfront.ResponseHeadersPolicy(
            self,
            "SecurityHeaders",
            response_headers_policy_name=f"{prefix}-portal-headers-{env_name}",
            security_headers_behavior=cloudfront.ResponseSecurityHeadersBehavior(
                strict_transport_security=cloudfront.ResponseHeadersStrictTransportSecurity(
                    access_control_max_age=Duration.days(365), include_subdomains=True, override=True
                ),
                content_type_options=cloudfront.ResponseHeadersContentTypeOptions(override=True),
                frame_options=cloudfront.ResponseHeadersFrameOptions(
                    frame_option=cloudfront.HeadersFrameOption.DENY, override=True
                ),
                referrer_policy=cloudfront.ResponseHeadersReferrerPolicy(
                    referrer_policy=cloudfront.HeadersReferrerPolicy.STRICT_ORIGIN_WHEN_CROSS_ORIGIN, override=True
                ),
            ),
        )

        # SPA routing: only extension-less paths (e.g. /modulo/03) are rewritten to /index.html.
        # Missing assets keep failing loudly instead of returning HTML disguised as JS.
        spa_rewrite = cloudfront.Function(
            self,
            "SpaRewriteFunction",
            function_name=f"{prefix}-portal-spa-rewrite-{env_name}",
            runtime=cloudfront.FunctionRuntime.JS_2_0,
            code=cloudfront.FunctionCode.from_inline(
                "function handler(event) {\n"
                "  var request = event.request;\n"
                "  var last = request.uri.split('/').pop();\n"
                "  if (last.indexOf('.') === -1) { request.uri = '/index.html'; }\n"
                "  return request;\n"
                "}"
            ),
        )

        distribution = cloudfront.Distribution(
            self,
            "PortalDistribution",
            comment=f"{app_config['customer_name']} - Agentic AI Workshop portal ({env_name})",
            default_root_object="index.html",
            minimum_protocol_version=cloudfront.SecurityPolicyProtocol.TLS_V1_2_2021,
            price_class=cloudfront.PriceClass.PRICE_CLASS_ALL,
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_control(bucket),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
                response_headers_policy=security_headers,
                compress=True,
                function_associations=[
                    cloudfront.FunctionAssociation(
                        function=spa_rewrite, event_type=cloudfront.FunctionEventType.VIEWER_REQUEST
                    )
                ],
            ),
        )

        public_config = {key: app_config.get(key, "") for key in PUBLIC_CONFIG_KEYS}

        # 1) Hashed build assets: cached forever and NEVER pruned, so tabs opened on an
        #    older version keep loading their chunks after a redeploy.
        assets = s3_deploy.BucketDeployment(
            self,
            "PortalAssetsDeployment",
            sources=[s3_deploy.Source.asset(str(FRONTEND_DIST / "assets"))],
            destination_bucket=bucket,
            destination_key_prefix="assets/",
            cache_control=[s3_deploy.CacheControl.from_string("public, max-age=31536000, immutable")],
            prune=False,
            memory_limit=512,
        )
        # 2) Diagrams (not hashed): short cache
        diagrams = s3_deploy.BucketDeployment(
            self,
            "PortalDiagramsDeployment",
            sources=[s3_deploy.Source.asset(str(FRONTEND_DIST / "diagrams"))],
            destination_bucket=bucket,
            destination_key_prefix="diagrams/",
            cache_control=[s3_deploy.CacheControl.from_string("public, max-age=3600")],
            prune=False,
            memory_limit=512,
        )
        # 3) Entry points: always revalidated, published AFTER the assets they reference
        entry = s3_deploy.BucketDeployment(
            self,
            "PortalEntryDeployment",
            sources=[
                s3_deploy.Source.asset(str(FRONTEND_DIST), exclude=["assets", "assets/*", "diagrams", "diagrams/*", "config.json"]),
                s3_deploy.Source.json_data("config.json", public_config),
            ],
            destination_bucket=bucket,
            cache_control=[s3_deploy.CacheControl.from_string("no-cache, must-revalidate")],
            prune=False,
            distribution=distribution,
            distribution_paths=["/*"],
            memory_limit=512,
        )
        entry.node.add_dependency(assets)
        entry.node.add_dependency(diagrams)

        CfnOutput(self, "PortalBucketName", value=bucket.bucket_name)
        CfnOutput(self, "CloudFrontDistributionId", value=distribution.distribution_id)
        CfnOutput(
            self,
            "CloudFrontURL",
            value=f"https://{distribution.distribution_domain_name}",
            description="Workshop portal URL (CloudFront default domain)",
        )
