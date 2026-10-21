"""Private subprocess entry point: one real AIAgent conversation per request."""

import contextlib
import json
import os
from pathlib import Path
import sys
import threading


def main():
    output = sys.stdout
    request = json.loads(sys.stdin.readline())
    def emit(event):
        output.write(json.dumps(event) + "\n")
        output.flush()
    with contextlib.redirect_stdout(sys.stderr):
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
            emit(dict(type="result", memory=memory, entries=len(store.memory_entries)))
            return
        transport_lock = threading.Lock()
        def handler(name):
            def invoke(args, **kwargs):
                with transport_lock:
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

        agent = BoundedAgent(model=request["model"], provider="custom",
                        api_mode="chat_completions", base_url=request["base_url"],
                        api_key=request["api_key"], max_iterations=request["max_steps"],
                        enabled_toolsets=["belive_support"] if request["tools"] else [],
                        quiet_mode=True, skip_context_files=True, skip_memory=True,
                        save_trajectories=False, tool_delay=0, max_tokens=2500)
        actual = {tool["function"]["name"] for tool in agent.tools}
        if actual != allowed:
            raise RuntimeError("HERMES_TOOLSET_MISMATCH")
        messages = request["messages"]
        system = "\n".join(m["content"] for m in messages if m["role"] == "system")
        system += "\nThe following native Hermes memory is approved style guidance only. Never copy factual claims.\n" + memory
        user = "\n".join(m["content"] for m in messages if m["role"] != "system")
        result = agent.run_conversation(user_message=user, system_message=system)
        if result.get("failed") or str(result.get("final_response", "")).startswith("API call failed"):
            raise RuntimeError("PROVIDER_FAILED")
        emit(dict(type="result", text=result.get("final_response", ""),
                  api_calls=result.get("api_calls", 0), tools=sorted(actual),
                  memory_entries=len(store.memory_entries)))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # No provider response, prompt or key is emitted as an error diagnostic.
        print(json.dumps(dict(type="error", code="HERMES_NATIVE_" + type(exc).__name__.upper())), flush=True)
