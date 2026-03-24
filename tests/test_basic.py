"""
Magic Debug Tests
"""

import sys
import os
import pytest

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestDAPProtocol:
    """DAP 协议测试"""
    
    def test_message_structure(self):
        """测试消息结构"""
        from core.dap import DAPRequest, DAPResponse, DAPEvent
        
        # 测试请求
        request = DAPRequest(
            type="request",
            raw={"seq": 1, "command": "initialize"},
            seq=1,
            command="initialize"
        )
        assert request.command == "initialize"
        
        # 测试响应
        response = DAPResponse(
            type="response",
            raw={"success": True},
            request_seq=1,
            success=True,
            command="initialize"
        )
        assert response.success is True
        
        # 测试事件
        event = DAPEvent(
            type="event",
            raw={"event": "stopped"},
            event="stopped",
            body={"reason": "breakpoint"}
        )
        assert event.event == "stopped"


class TestStateModel:
    """状态模型测试"""
    
    def test_debug_state_initialization(self):
        """测试状态初始化"""
        from core.state import DebugState, DebugStatus
        
        state = DebugState()
        assert state.status == DebugStatus.IDLE
        assert state.current_thread_id == 0
        assert state.threads == []
        assert state.stack_frames == []
    
    def test_state_to_dict(self):
        """测试状态序列化"""
        from core.state import DebugState
        
        state = DebugState()
        d = state.to_dict()
        
        assert "status" in d
        assert "threads" in d
        assert "stackFrames" in d
    
    def test_state_summary(self):
        """测试状态摘要"""
        from core.state import DebugState
        
        state = DebugState()
        summary = state.to_summary()
        
        assert "status" in summary
        assert "program" in summary


class TestLLDBAdapter:
    """LLDB 适配器测试"""
    
    def test_adapter_initialization(self):
        """测试适配器初始化"""
        from adapters.lldb import LLDBAdapter, LLDBConfig
        
        config = LLDBConfig()
        adapter = LLDBAdapter(config)
        
        assert adapter.config is not None
    
    def test_launch_arguments(self):
        """测试启动参数生成"""
        from adapters.lldb import LLDBAdapter
        
        adapter = LLDBAdapter()
        args = adapter.get_launch_arguments(
            program="/path/to/program",
            args=["--help"],
            cwd="/home/user"
        )
        
        assert args["program"] == "/path/to/program"
        assert args["args"] == ["--help"]
        assert args["cwd"] == "/home/user"


class TestRPCProtocol:
    """RPC 协议测试"""
    
    def test_request_structure(self):
        """测试请求结构"""
        from server.rpc import RPCRequest
        
        request = RPCRequest(id=1, method="ping", params={})
        assert request.id == 1
        assert request.method == "ping"
    
    def test_response_structure(self):
        """测试响应结构"""
        from server.rpc import RPCResponse
        
        response = RPCResponse(id=1, result={"success": True})
        d = response.to_dict()
        
        assert d["id"] == 1
        assert d["result"]["success"] is True


class TestController:
    """控制器测试"""
    
    def test_config_structure(self):
        """测试配置结构"""
        from core.controller import DebugConfig
        
        config = DebugConfig(
            program="/path/to/program",
            args=["--help"],
            stop_on_entry=True
        )
        
        assert config.program == "/path/to/program"
        assert config.args == ["--help"]
        assert config.stop_on_entry is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
