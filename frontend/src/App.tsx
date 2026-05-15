// App 根组件
// =========
// 路由：
//   /auth   登录/注册
//   /game   主游戏页（受保护，未登录跳 /auth）
//   /       自动按 token 跳转
import { Navigate, Route, BrowserRouter, Routes } from "react-router-dom";
import { Auth } from "./pages/Auth";
import { Game } from "./pages/Game";

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const token = localStorage.getItem("ai_dm_token");
  if (!token) return <Navigate to="/auth" replace />;
  return <>{children}</>;
}

function RootRedirect() {
  const token = localStorage.getItem("ai_dm_token");
  return <Navigate to={token ? "/game" : "/auth"} replace />;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/auth" element={<Auth />} />
        <Route
          path="/game"
          element={
            <ProtectedRoute>
              <Game />
            </ProtectedRoute>
          }
        />
        <Route path="/" element={<RootRedirect />} />
        <Route path="*" element={<RootRedirect />} />
      </Routes>
    </BrowserRouter>
  );
}
