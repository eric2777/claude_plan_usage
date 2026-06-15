import json
import os
import subprocess
import tempfile

SWIFT_SOURCE = r"""import Foundation

guard let sessionKey = ProcessInfo.processInfo.environment["SESSION_KEY"] else {
    fputs("SESSION_KEY not set\n", stderr); exit(1)
}

func makeReq(_ urlStr: String) -> URLRequest {
    var req = URLRequest(url: URL(string: urlStr)!, timeoutInterval: 15)
    req.setValue("sessionKey=\(sessionKey)", forHTTPHeaderField: "Cookie")
    req.setValue("web_claude_ai", forHTTPHeaderField: "anthropic-client-platform")
    req.setValue("application/json", forHTTPHeaderField: "Accept")
    return req
}

func orNull(_ v: Any?) -> Any { return v ?? NSNull() }

let group = DispatchGroup()
group.enter()
URLSession.shared.dataTask(with: makeReq("https://claude.ai/api/organizations")) { d, resp, _ in
    guard let data = d,
          (resp as? HTTPURLResponse)?.statusCode == 200,
          let orgs = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]],
          let orgId = orgs.first?["uuid"] as? String else {
        fputs("Failed to fetch org\n", stderr); exit(1)
    }
    URLSession.shared.dataTask(with: makeReq("https://claude.ai/api/organizations/\(orgId)/usage")) { d2, resp2, _ in
        guard let data2 = d2,
              (resp2 as? HTTPURLResponse)?.statusCode == 200,
              let usage = try? JSONSerialization.jsonObject(with: data2) as? [String: Any] else {
            fputs("Failed to fetch usage\n", stderr); exit(1)
        }
        let fiveHour = usage["five_hour"] as? [String: Any] ?? [:]
        let sevenDay = usage["seven_day"] as? [String: Any] ?? [:]
        let out: [String: Any] = [
            "session_pct": Int((fiveHour["utilization"] as? Double) ?? 0),
            "weekly_pct": Int((sevenDay["utilization"] as? Double) ?? 0),
            "session_reset_at": orNull(fiveHour["resets_at"]),
            "weekly_reset_at": orNull(sevenDay["resets_at"]),
        ]
        guard let jsonData = try? JSONSerialization.data(withJSONObject: out),
              let jsonStr = String(data: jsonData, encoding: .utf8) else {
            fputs("Failed to encode output\n", stderr); exit(1)
        }
        print(jsonStr)
        group.leave()
    }.resume()
}.resume()
group.wait()
"""


def _ensure_fetch_binary(binary_path):
    if os.path.exists(binary_path):
        return
    os.makedirs(os.path.dirname(binary_path), exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".swift", mode="w", delete=False) as f:
        f.write(SWIFT_SOURCE)
        src_path = f.name
    try:
        subprocess.run(["swiftc", src_path, "-o", binary_path], check=True, capture_output=True)
    finally:
        os.unlink(src_path)


def fetch_usage(session_key, binary_path):
    _ensure_fetch_binary(binary_path)
    result = subprocess.run(
        [binary_path],
        env={**os.environ, "SESSION_KEY": session_key},
        capture_output=True, text=True, timeout=20,
    )
    if result.returncode != 0:
        raise RuntimeError(f"fetch binary failed: {result.stderr.strip()}")
    return json.loads(result.stdout)
