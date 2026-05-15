// 登录 + 注册一页两 tab
// ====================
// - 不分两个路由，少一次跳转
// - 注册成功后自动登录（前端再调 login 拿 token）
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { login, register, ApiError } from "../api";

export function Auth() {
  const navigate = useNavigate();
  const [tab, setTab] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      if (tab === "register") {
        await register(username, password);
      }
      await login(username, password);
      navigate("/game");
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("网络异常");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-full flex items-center justify-center px-4">
      <div className="w-full max-w-md bg-stone-800/90 border border-stone-700 rounded-lg p-8 shadow-2xl">
        <h1 className="text-3xl text-parchment text-center mb-1">AI Dungeon Master</h1>
        <p className="text-stone-400 text-sm text-center mb-6">LLM 驱动的文字冒险</p>

        <div className="flex border-b border-stone-700 mb-6">
          <button
            type="button"
            className={`flex-1 py-2 text-sm transition ${
              tab === "login" ? "text-parchment border-b-2 border-amber-600" : "text-stone-500"
            }`}
            onClick={() => setTab("login")}
          >
            登录
          </button>
          <button
            type="button"
            className={`flex-1 py-2 text-sm transition ${
              tab === "register" ? "text-parchment border-b-2 border-amber-600" : "text-stone-500"
            }`}
            onClick={() => setTab("register")}
          >
            注册
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-stone-400 text-sm mb-1">用户名</label>
            <input
              type="text"
              required
              minLength={3}
              maxLength={64}
              pattern="^[a-zA-Z0-9_]+$"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full px-3 py-2 bg-stone-900 border border-stone-700 rounded text-parchment focus:outline-none focus:border-amber-600"
            />
            <p className="text-stone-600 text-xs mt-1">3-64 位字母/数字/下划线</p>
          </div>
          <div>
            <label className="block text-stone-400 text-sm mb-1">密码</label>
            <input
              type="password"
              required
              minLength={6}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-3 py-2 bg-stone-900 border border-stone-700 rounded text-parchment focus:outline-none focus:border-amber-600"
            />
          </div>

          {error && (
            <div className="text-red-400 text-sm bg-red-900/30 border border-red-800 rounded px-3 py-2">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2 bg-amber-700 hover:bg-amber-600 disabled:opacity-50 text-parchment rounded transition"
          >
            {loading ? "请稍候..." : tab === "login" ? "登录" : "注册并登录"}
          </button>
        </form>
      </div>
    </div>
  );
}
