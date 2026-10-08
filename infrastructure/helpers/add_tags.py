import aws_cdk as cdk


def add_tags_to_app(app: cdk.App, tags: dict, app_config: dict) -> None:
    for key, value in tags.items():
        cdk.Tags.of(app).add(key, value)
    cdk.Tags.of(app).add("Environment", app_config["deployment_environment"])
    cdk.Tags.of(app).add("Customer", app_config["customer_id"])
    cdk.Tags.of(app).add("ResourcePrefix", app_config["resource_prefix"])
