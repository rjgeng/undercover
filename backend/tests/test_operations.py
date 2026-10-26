from fastapi.routing import APIRoute

from backend.main import app


def test_every_operation_follows_the_tech_stack():
    routes = [route for route in app.routes if isinstance(route, APIRoute)]
    assert routes
    for route in routes:
        assert route.operation_id, route.path
        assert route.description, route.path
        assert "\n" not in route.description, route.path


def test_no_operation_has_optional_inputs():
    schema = app.openapi()
    for path in schema["paths"].values():
        for operation in path.values():
            for parameter in operation.get("parameters", []):
                assert parameter["required"], operation["operationId"]
            if "requestBody" in operation:
                ref = operation["requestBody"]["content"]["application/json"]
                name = ref["schema"]["$ref"].split("/")[-1]
                body = schema["components"]["schemas"][name]
                assert set(body["required"]) == set(body["properties"]), name
