"""Private worker: fresh AIAgent and current memory projection for each request."""

import contextlib
import json
import os
from pathlib import Path
import sys
import threading


def handle_request(request):
    output = sys.stdout
    def emit(event):
        output.write(json.dumps(event) + "\n")
        output.flush()
    with contextlib.redirect_stdout(sys.stderr):
        # Hermes 0.22 enables deferred tool search automatically.  This worker
        # is intentionally limited to the tools supplied by BeLive, so turn it
        # off in the request-specific HERMES_HOME before importing the agent.
        from hermes_cli.config import atomic_config_write, get_config_path, read_raw_config

        config = read_raw_config()
        tool_config = config.setdefault("tools", {})
        if not isinstance(tool_config, dict):
            tool_config = {}
            config["tools"] = tool_config
        search_config = tool_config.setdefault("tool_search", {})
        if not isinstance(search_config, dict):
            search_config = {}
            tool_config["tool_search"] = search_config
        if search_config.get("enabled") != "off":
            search_config["enabled"] = "off"
            atomic_config_write(get_config_path(), config)

        from run_agent import AIAgent
        from tools.registry import registry
        from tools.memory_tool import MemoryStore

        store = MemoryStore()
        store.load_from_disk()
        # The dedicated store is a projection of CURRENT operator feedback. Rejections
        # revoke old examples on the next run instead of surviving in native memory.
        for entry in list(store.memory_entries):
            store.remove("memory", entry)
        for example in request["examples"][:5]:
            content = "Approved style example, not verified facts. Feedback version " + str(example["version_id"]) + ": " + example["approved_reply"][:320]
            outcome = store.add("memory", content)
            if not outcome.get("success"):
                continue
        store.load_from_disk()
        memory = store.format_for_system_prompt("memory") or ""
        if request["mode"] == "memory":
            emit(dict(type="result",engine='hermes-native',agent_class='run_agent.AIAgent',version=request.get('runtime_version'),commit=request.get('runtime_commit'), memory=memory, entries=len(store.memory_entries),memory_entries=len(store.memory_entries),executed_tools=[],api_calls=0))
            return
        transport_lock = threading.Lock()
        executed=[]
        def handler(name):
            def invoke(args, **kwargs):
                with transport_lock:
                    executed.append(name)
                    emit(dict(type="tool", name=name, arguments=args))
                    return sys.stdin.readline().strip()
            return invoke
        for tool in request["tools"]:
            registry.register(name=tool["name"], toolset="belive_support",
                              schema=tool, handler=handler(tool["name"]))
        allowed = {tool["name"] for tool in request["tools"]}
        class BoundedAgent(AIAgent):
            def _execute_tool_calls(self, assistant_message, *args, **kwargs):
                calls = (assistant_message.get("tool_calls", []) if isinstance(assistant_message, dict)
                         else getattr(assistant_message, "tool_calls", []))
                for call in calls or []:
                    if self._get_tool_call_name_static(call) not in allowed:
                        raise RuntimeError("HERMES_TOOL_OUTSIDE_ALLOWLIST")
                return super()._execute_tool_calls(assistant_message, *args, **kwargs)

            def _invoke_tool(self, function_name, function_args, *args, **kwargs):
                if function_name not in allowed:
                    return json.dumps({"error": "Tool is outside this project's allowlist"})
                return super()._invoke_tool(function_name, function_args, *args, **kwargs)

        from urllib.parse import urlsplit
        endpoint = urlsplit(request["base_url"])
        local_ollama = endpoint.scheme == "http" and endpoint.hostname in {"localhost", "127.0.0.1", "::1"}
        options = {}
        if request.get('response_schema') or local_ollama:
            response_format = {"type": "json_object"}
            if request.get("response_schema"):
                response_format = {"type": "json_schema", "json_schema": {
                    "name": "support_response", "strict": True, "schema": request["response_schema"]
                }}
            options["request_overrides"] = {"response_format": response_format, "reasoning_effort": "none"}
            if not local_ollama:options['request_overrides']['store']=False
        agent = BoundedAgent(model=request["model"], provider="custom",
                        api_mode="chat_completions", base_url=request["base_url"],
                        api_key=request["api_key"], max_iterations=request["max_steps"],
                        enabled_toolsets=["belive_support"] if request["tools"] else [],
                        quiet_mode=True, skip_context_files=True, skip_memory=False,skip_background_review=True,
                        save_trajectories=False, tool_delay=0, max_tokens=request.get('max_tokens',2500), **options)
        actual = {tool["function"]["name"] for tool in agent.tools}
        if actual != allowed:
            raise RuntimeError("HERMES_TOOLSET_MISMATCH")
        native_memory=getattr(agent,'_memory_store',None)
        if store.memory_entries and (native_memory is None or native_memory.memory_entries!=store.memory_entries):raise RuntimeError('HERMES_MEMORY_PROJECTION_MISMATCH')
        messages = request["messages"]
        system = "\n".join(m["content"] for m in messages if m["role"] == "system")
        system += "\nNative Hermes memory contains approved writing guidance only. It is not proof of company facts or policy. Use the current evidence tool for operational facts."
        parts=[m['content'] for m in messages if m['role']!='system']
        if any(isinstance(x,list) for x in parts):
            user=[]
            for part in parts:user.extend(part if isinstance(part,list) else [{'type':'text','text':part}])
        else:user='\n'.join(parts)
        result = agent.run_conversation(user_message=user, system_message=system)
        if result.get("failed") or str(result.get("final_response", "")).startswith("API call failed"):
            raise RuntimeError("PROVIDER_FAILED")
        emit(dict(type="result",engine='hermes-native',agent_class='run_agent.AIAgent',version=request.get('runtime_version'),commit=request.get('runtime_commit'),executed_tools=executed,text=result.get("final_response", ""),
                  api_calls=result.get("api_calls", 0), tools=sorted(actual),native_memory_loaded=native_memory is not None,
                  memory_entries=len(store.memory_entries)))


def main():
    while True:
        line=sys.stdin.readline()
        if not line:return
        try:handle_request(json.loads(line))
        except Exception as exc:
            # No provider response, prompt or key is emitted as an error diagnostic.
            fixed = {"HERMES_TOOL_OUTSIDE_ALLOWLIST", "HERMES_TOOLSET_MISMATCH"}
            code = str(exc) if str(exc) in fixed else "HERMES_NATIVE_" + type(exc).__name__.upper()
            event=dict(type='error',code=code)
            if isinstance(exc,ModuleNotFoundError):event['missing_module']=exc.name
            print(json.dumps(event),flush=True)


if __name__ == "__main__":main()
