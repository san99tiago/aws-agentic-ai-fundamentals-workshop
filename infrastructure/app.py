#!/usr/bin/env python3
"""CDK entrypoint for the parametrized Agentic AI Workshop."""

import os

import aws_cdk as cdk

from helpers.add_tags import add_tags_to_app
from helpers.config import resolve_app_config
from stacks.foundation_stack import FoundationStack
from stacks.frontend_stack import FrontendStack

app = cdk.App()

DEPLOYMENT_ENVIRONMENT = os.environ.get("DEPLOYMENT_ENVIRONMENT", "dev")
APP_CONFIG = resolve_app_config(app.node.try_get_context("app_config")[DEPLOYMENT_ENVIRONMENT])
PREFIX = APP_CONFIG["resource_prefix"]
ENV = cdk.Environment(
    account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
    region=APP_CONFIG["aws_region"],
)

FoundationStack(
    app,
    f"{PREFIX}-foundation-{DEPLOYMENT_ENVIRONMENT}",
    app_config=APP_CONFIG,
    env=ENV,
    description=f"Agentic AI Workshop foundation for {APP_CONFIG['customer_name']} (S3, API GW + Lambda, IAM roles)",
)

if APP_CONFIG["deploy_frontend"]:
    FrontendStack(
        app,
        f"{PREFIX}-portal-{DEPLOYMENT_ENVIRONMENT}",
        app_config=APP_CONFIG,
        env=ENV,
        description=f"Agentic AI Workshop portal for {APP_CONFIG['customer_name']} (S3 + CloudFront OAC)",
    )

add_tags_to_app(app, app.node.try_get_context("tags"), APP_CONFIG)
app.synth()
