"""CDK unit tests: synth with the generic ACME pack and assert the security guardrails
of the workshop (private buckets, CloudFront OAC, IAM-protected API, scoped trust)."""

import json
import os
import sys
from pathlib import Path

import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Match, Template

INFRA = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(INFRA))

from helpers.config import resolve_app_config  # noqa: E402
from stacks.foundation_stack import FoundationStack  # noqa: E402
from stacks.frontend_stack import FRONTEND_DIST, FrontendStack  # noqa: E402

ENV = cdk.Environment(account="111111111111", region="us-east-1")


@pytest.fixture(scope="module")
def app_config(monkeypatch_module=None):
    overrides = {"CUSTOMER_ID": "acme", "RESOURCE_PREFIX": "test-workshop", "AGENT_NAME": "AgentBot"}
    old = {k: os.environ.get(k) for k in overrides}
    os.environ.update(overrides)
    cdk_json = json.loads((INFRA / "cdk.json").read_text())
    config = resolve_app_config(cdk_json["context"]["app_config"]["dev"])
    yield config
    for key, value in old.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


@pytest.fixture(scope="module")
def foundation(app_config):
    app = cdk.App()
    return Template.from_stack(FoundationStack(app, "Foundation", app_config=app_config, env=ENV))


def test_customer_parameters_are_applied(app_config):
    assert app_config["customer_id"] == "acme"
    assert app_config["resource_prefix"] == "test-workshop"


def test_buckets_are_private_and_encrypted(foundation):
    foundation.resource_count_is("AWS::S3::Bucket", 2)
    foundation.all_resources_properties(
        "AWS::S3::Bucket",
        {
            "PublicAccessBlockConfiguration": {
                "BlockPublicAcls": True,
                "BlockPublicPolicy": True,
                "IgnorePublicAcls": True,
                "RestrictPublicBuckets": True,
            },
            "BucketEncryption": Match.any_value(),
        },
    )
    assert not foundation.find_resources("AWS::S3::Bucket", {"Properties": {"WebsiteConfiguration": Match.any_value()}})


def test_banking_api_requires_iam_and_no_function_urls(foundation):
    methods = foundation.find_resources("AWS::ApiGateway::Method")
    business = [m for m in methods.values() if m["Properties"]["HttpMethod"] != "OPTIONS"]
    assert len(business) == 5
    assert all(m["Properties"]["AuthorizationType"] == "AWS_IAM" for m in business)
    foundation.resource_count_is("AWS::Lambda::Url", 0)


def test_agentcore_roles_have_confused_deputy_protection(foundation):
    roles = foundation.find_resources("AWS::IAM::Role")
    agentcore_roles = [
        r for r in roles.values()
        if "bedrock-agentcore.amazonaws.com" in json.dumps(r["Properties"]["AssumeRolePolicyDocument"])
    ]
    assert len(agentcore_roles) == 3  # gateway, harness, runtime
    for role in agentcore_roles:
        statement = role["Properties"]["AssumeRolePolicyDocument"]["Statement"][0]
        assert "aws:SourceAccount" in statement["Condition"]["StringEquals"]
        assert "aws:SourceArn" in statement["Condition"]["ArnLike"]


def test_no_security_group_open_to_world(foundation):
    for sg in foundation.find_resources("AWS::EC2::SecurityGroup").values():
        assert "0.0.0.0/0" not in json.dumps(sg["Properties"].get("SecurityGroupIngress", []))


@pytest.mark.skipif(not (FRONTEND_DIST / "index.html").exists(), reason="frontend not built")
def test_portal_uses_cloudfront_oac(app_config):
    app = cdk.App()
    template = Template.from_stack(FrontendStack(app, "Portal", app_config=app_config, env=ENV))
    template.resource_count_is("AWS::CloudFront::OriginAccessControl", 1)
    template.has_resource_properties(
        "AWS::CloudFront::Distribution",
        {"DistributionConfig": Match.object_like({"DefaultCacheBehavior": Match.object_like({"ViewerProtocolPolicy": "redirect-to-https"})})},
    )
