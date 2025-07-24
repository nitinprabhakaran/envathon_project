# debug_claude_connectivity.py - Run this in the streamlit container to debug Claude API issues
import os
import json
import time
import socket
from datetime import datetime

def log_with_timestamp(message):
    """Log message with timestamp"""
    print(f"[{datetime.now().isoformat()}] {message}")

def test_environment():
    """Test environment variables and package availability"""
    log_with_timestamp("=== ENVIRONMENT TEST ===")
    
    # Check API key
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        log_with_timestamp(f"✅ ANTHROPIC_API_KEY found: {api_key[:15]}...")
    else:
        log_with_timestamp("❌ ANTHROPIC_API_KEY not found")
        return False
    
    # Check anthropic package
    try:
        import anthropic
        log_with_timestamp(f"✅ anthropic package available: {anthropic.__version__}")
    except ImportError as e:
        log_with_timestamp(f"❌ anthropic package not installed: {e}")
        return False
    
    # Check httpx
    try:
        import httpx
        log_with_timestamp(f"✅ httpx package available: {httpx.__version__}")
    except ImportError as e:
        log_with_timestamp(f"❌ httpx package not installed: {e}")
        return False
    
    return True

def test_basic_connectivity():
    """Test basic network connectivity"""
    log_with_timestamp("=== BASIC CONNECTIVITY TEST ===")
    
    # Test DNS resolution
    try:
        ip = socket.gethostbyname("api.anthropic.com")
        log_with_timestamp(f"✅ DNS Resolution: api.anthropic.com -> {ip}")
    except Exception as e:
        log_with_timestamp(f"❌ DNS Resolution failed: {e}")
        return False
    
    # Test basic socket connection
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        result = sock.connect_ex(("api.anthropic.com", 443))
        if result == 0:
            log_with_timestamp("✅ Socket connection to api.anthropic.com:443 successful")
        else:
            log_with_timestamp(f"❌ Socket connection failed: error code {result}")
        sock.close()
    except Exception as e:
        log_with_timestamp(f"❌ Socket test failed: {e}")
        return False
    
    return True

def test_httpx_connectivity():
    """Test HTTP connectivity using httpx"""
    log_with_timestamp("=== HTTPX CONNECTIVITY TEST ===")
    
    try:
        import httpx
        
        # Test basic HTTP request
        with httpx.Client(timeout=30.0) as client:
            response = client.get("https://httpbin.org/get")
            log_with_timestamp(f"✅ Basic HTTP request successful: {response.status_code}")
    except Exception as e:
        log_with_timestamp(f"❌ Basic HTTP request failed: {e}")
        return False
    
    return True

def test_anthropic_client():
    """Test anthropic client initialization and simple request"""
    log_with_timestamp("=== ANTHROPIC CLIENT TEST ===")
    
    try:
        import anthropic
        
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            log_with_timestamp("❌ No API key available")
            return False
        
        # Test client initialization
        client = anthropic.Anthropic(
            api_key=api_key,
            timeout=30.0
        )
        log_with_timestamp("✅ Anthropic client initialized")
        
        # Test simple API call
        log_with_timestamp("🔄 Testing simple API call...")
        response = client.messages.create(
            model="claude-3-haiku-20240307",  # Use fastest model for testing
            max_tokens=5,
            messages=[{"role": "user", "content": "Hi"}]
        )
        log_with_timestamp(f"✅ API call successful: {response.content[0].text}")
        return True
        
    except Exception as e:
        log_with_timestamp(f"❌ Anthropic client test failed: {type(e).__name__}: {str(e)}")
        
        # Detailed error analysis
        error_str = str(e).lower()
        if "connection" in error_str:
            log_with_timestamp("   🔗 Likely network connection issue")
        elif "ssl" in error_str or "certificate" in error_str:
            log_with_timestamp("   🔒 Likely SSL/Certificate issue")
        elif "timeout" in error_str:
            log_with_timestamp("   ⏰ Request timeout")
        elif "api" in error_str and "key" in error_str:
            log_with_timestamp("   🔑 API key issue")
        elif "rate" in error_str or "limit" in error_str:
            log_with_timestamp("   🚦 Rate limiting")
        
        return False

def test_docker_networking():
    """Test Docker-specific networking issues"""
    log_with_timestamp("=== DOCKER NETWORKING TEST ===")
    
    # Check if we're in Docker
    try:
        with open('/proc/1/cgroup', 'r') as f:
            content = f.read()
            if 'docker' in content or 'containerd' in content:
                log_with_timestamp("✅ Running inside Docker container")
            else:
                log_with_timestamp("ℹ️ Not running in Docker container")
    except:
        log_with_timestamp("❓ Cannot determine container status")
    
    # Check DNS servers
    try:
        with open('/etc/resolv.conf', 'r') as f:
            dns_content = f.read()
            log_with_timestamp(f"📋 DNS configuration:\n{dns_content}")
    except:
        log_with_timestamp("❌ Cannot read DNS configuration")
    
    # Test external connectivity
    external_hosts = [
        "8.8.8.8",  # Google DNS
        "1.1.1.1",  # Cloudflare DNS
        "google.com",
        "api.anthropic.com"
    ]
    
    for host in external_hosts:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            if host in ["8.8.8.8", "1.1.1.1"]:
                # Test DNS servers on port 53
                result = sock.connect_ex((host, 53))
            else:
                # Test HTTP hosts on port 443
                result = sock.connect_ex((host, 443))
            
            if result == 0:
                log_with_timestamp(f"✅ Can reach {host}")
            else:
                log_with_timestamp(f"❌ Cannot reach {host}: error {result}")
            sock.close()
        except Exception as e:
            log_with_timestamp(f"❌ Error testing {host}: {e}")

def main():
    """Run all connectivity tests"""
    log_with_timestamp("🔍 Starting Claude API connectivity diagnosis...")
    log_with_timestamp("=" * 60)
    
    # Run all tests
    tests = [
        ("Environment", test_environment),
        ("Basic Connectivity", test_basic_connectivity),
        ("HTTPX Connectivity", test_httpx_connectivity),
        ("Docker Networking", test_docker_networking),
        ("Anthropic Client", test_anthropic_client),
    ]
    
    results = {}
    for test_name, test_func in tests:
        try:
            results[test_name] = test_func()
        except Exception as e:
            log_with_timestamp(f"❌ Test '{test_name}' crashed: {e}")
            results[test_name] = False
        
        log_with_timestamp("")  # Add spacing
    
    # Summary
    log_with_timestamp("=" * 60)
    log_with_timestamp("📊 TEST SUMMARY:")
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        log_with_timestamp(f"   {test_name}: {status}")
    
    # Recommendations
    log_with_timestamp("")
    log_with_timestamp("💡 RECOMMENDATIONS:")
    
    if not results.get("Environment", False):
        log_with_timestamp("   1. Install missing packages: pip install anthropic")
        log_with_timestamp("   2. Set ANTHROPIC_API_KEY environment variable")
    
    if not results.get("Basic Connectivity", False):
        log_with_timestamp("   1. Check Docker network configuration")
        log_with_timestamp("   2. Verify internet connectivity from container")
        log_with_timestamp("   3. Check firewall/proxy settings")
    
    if not results.get("Anthropic Client", False):
        log_with_timestamp("   1. Try switching to LLM_PROVIDER=mock for testing")
        log_with_timestamp("   2. Check API key validity at https://console.anthropic.com")
        log_with_timestamp("   3. Try running outside Docker to isolate network issues")

if __name__ == "__main__":
    main()