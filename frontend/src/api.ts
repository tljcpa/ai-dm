// 后端 API 客户端
// ==============
// - 走 /api 前缀（Vite 开发期 proxy 到 :8765；生产期 Nginx 做同样的事）
// - JWT 存在 localStorage，每次请求带 Authorization: Bearer
// - 所有失败统一抛 ApiError，调用端 catch 后渲染错误信息

const BASE = "/api";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

// ===== 类型定义（和后端 Pydantic 对齐）=====

export interface UserResponse {
  id: number;
  username: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface PlayerStats {
  hp: number;
  max_hp: number;
  mp: number;
  max_mp: number;
  level: number;
  gold: number;
  inventory: string[];
}

export interface Scene {
  location: string;
  description: string;
  present_npcs: string[];
}

export interface GameState {
  player: PlayerStats;
  scene: Scene;
  story_flags: Record<string, boolean>;
  turn_count: number;
  long_term_summary: string;
  recent_history: Array<{ user: string; dm: string }>;
}

export interface SessionSummary {
  id: number;
  title: string;
  turn_count: number;
  location: string;
  updated_at: string;
}

export interface TurnResponse {
  narration: string;
  options: string[];
  state: GameState;
}

// ===== 工具：HTTP 调用封装 =====

function getToken(): string | null {
  return localStorage.getItem("ai_dm_token");
}

export function setToken(token: string | null) {
  if (token === null) {
    localStorage.removeItem("ai_dm_token");
  } else {
    localStorage.setItem("ai_dm_token", token);
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  auth: boolean = true,
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> | undefined),
  };
  if (auth) {
    const token = getToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }

  const resp = await fetch(`${BASE}${path}`, { ...options, headers });

  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`;
    try {
      const body = await resp.json();
      detail = body.detail ?? detail;
    } catch {
      // 忽略 JSON 解析失败
    }
    throw new ApiError(resp.status, detail);
  }
  // 204 No Content（DELETE 接口）
  if (resp.status === 204) return undefined as T;
  return resp.json() as Promise<T>;
}

// ===== 鉴权 =====

export async function register(username: string, password: string): Promise<UserResponse> {
  return request<UserResponse>("/auth/register", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  }, false);
}

export async function login(username: string, password: string): Promise<TokenResponse> {
  const resp = await request<TokenResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  }, false);
  setToken(resp.access_token);
  return resp;
}

export async function getMe(): Promise<UserResponse> {
  return request<UserResponse>("/auth/me");
}

export function logout() {
  setToken(null);
}

// ===== 游戏 =====

export async function listSessions(): Promise<SessionSummary[]> {
  return request<SessionSummary[]>("/game/sessions");
}

export async function createSession(title: string = "新冒险"): Promise<SessionSummary> {
  return request<SessionSummary>("/game/sessions", {
    method: "POST",
    body: JSON.stringify({ title }),
  });
}

export async function getSessionState(id: number): Promise<GameState> {
  return request<GameState>(`/game/sessions/${id}`);
}

export async function playTurn(id: number, user_input: string): Promise<TurnResponse> {
  return request<TurnResponse>(`/game/sessions/${id}/turn`, {
    method: "POST",
    body: JSON.stringify({ user_input }),
  });
}

export async function deleteSession(id: number): Promise<void> {
  return request<void>(`/game/sessions/${id}`, { method: "DELETE" });
}
