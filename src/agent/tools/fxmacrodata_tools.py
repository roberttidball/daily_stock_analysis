"""Public macroeconomic tools consumed by the stock analysis agent."""

from copy import deepcopy
import os

from fxmacrodata_public import FXMacroDataClient, list_operations
from src.agent.tools.registry import ToolDefinition, ToolParameter, ToolPolicy


class FXMacroDataTool(ToolDefinition):
    """Keep nested public JSON Schemas intact in every DSA tool descriptor."""

    input_schema: dict

    def _params_json_schema(self) -> dict:
        return deepcopy(self.input_schema)

    def _descriptor_json_schema(self) -> dict:
        return self._params_json_schema()


def fxmacrodata_tool_names(*operations: str) -> list[str]:
    """Name tools for native specialist allowlists; no arguments selects all."""
    available = {operation.name for operation in list_operations()}
    selected = list(operations) if operations else [operation.name for operation in list_operations()]
    if any(operation not in available for operation in selected):
        raise ValueError("Unknown FXMacroData operation in specialist tool selection.")
    return [f"fxmacrodata_{operation}" for operation in selected]


def build_fxmacrodata_tools(client: FXMacroDataClient | None = None) -> list[FXMacroDataTool]:
    """Build read-only tools; the USD baseline works without configuration.

    An optional FXMACRODATA_API_KEY is read from the host environment at call
    time, never put into a tool schema, invocation argument or response.
    """
    def make_handler(operation_name):
        def handler(**arguments):
            provider = client or FXMacroDataClient(
                api_key=os.environ.get("FXMACRODATA_API_KEY") or "", timeout=30
            )
            try:
                response = provider.execute(operation_name, arguments).as_dict()
                response["provider_url"] = (
                    "https://fxmacrodata.com/?utm_source=daily_stock_analysis"
                    "&utm_medium=integration&utm_campaign=open_source_integrations&utm_content=app"
                )
                return response
            except Exception:
                # DSA logs propagated exceptions; never propagate a transport
                # exception or a request which could contain a credential.
                return {"operation": operation_name, "status": "unavailable", "records": [],
                        "error": "FXMacroData could not complete this request."}
            finally:
                if client is None:
                    provider.close()

        return handler

    result = []
    for operation in list_operations():
        required = operation.input_schema.get("required", [])
        parameters = [
            ToolParameter(
                name=name,
                type=schema.get("type", "object"),
                description=schema.get("description", name),
                required=name in required,
            )
            for name, schema in operation.input_schema.get("properties", {}).items()
        ]
        definition = FXMacroDataTool(
            name=f"fxmacrodata_{operation.name}",
            description=f"FXMacroData: {operation.description}",
            parameters=parameters,
            handler=make_handler(operation.name),
            category="market",
            policy=ToolPolicy.declared(
                read_only=True, permissions=["network"], timeout_seconds=35,
            ),
            timeout_seconds=35,
        )
        definition.input_schema = deepcopy(operation.input_schema)
        result.append(definition)
    return result
