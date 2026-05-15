// 游戏主页面
// ==========
// 左边大区：场景叙事 + 历史对话流（每条 DM 叙事走打字机效果）
// 右边小区：玩家状态卡片（HP/MP/金币/物品/位置/NPC）+ 存档切换
// 底部：输入框 + 建议选项按钮
//
// 打字机效果说明（D-018 见 DECISIONS.md）：
// - 不用真 SSE 流式，因为 LLM 输出必须等 JSON 完整解析才有 narration 字段
// - 前端拿到完整 narration 后用 useEffect + setInterval 按字渲染，30ms/字
// - 体感"流式"对玩家来说足够，少一层 SSE 复杂度
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ApiError,
  GameState,
  SessionSummary,
  TurnResponse,
  createSession,
  deleteSession,
  getSessionState,
  listSessions,
  logout as apiLogout,
  playTurn,
} from "../api";

interface ChatTurn {
  user?: string;
  dm: string;
  /** 是否还在打字机渲染中（最后一条 DM 叙事） */
  typing?: boolean;
}

export function Game() {
  const navigate = useNavigate();
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [state, setState] = useState<GameState | null>(null);
  const [history, setHistory] = useState<ChatTurn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastOptions, setLastOptions] = useState<string[]>([]);

  // 用于自动滚到底
  const scrollRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [history.length, history[history.length - 1]?.dm]);

  // 初次加载存档列表
  useEffect(() => {
    refreshSessions().catch((err) => {
      if (err instanceof ApiError && err.status === 401) {
        navigate("/auth");
      }
    });
  }, []);

  async function refreshSessions() {
    const list = await listSessions();
    setSessions(list);
    if (list.length > 0 && activeId === null) {
      await openSession(list[0].id);
    }
  }

  async function openSession(id: number) {
    setError(null);
    setActiveId(id);
    setHistory([]);
    setLastOptions([]);
    const s = await getSessionState(id);
    setState(s);
    // 把已有历史塞进 chat 流（不打字机，瞬时显示）
    const turns: ChatTurn[] = s.recent_history.map((t) => ({ user: t.user, dm: t.dm }));
    // 如果还没玩过任何回合，给个开场叙事（不调 LLM）
    if (turns.length === 0) {
      turns.push({
        dm: `${s.scene.description}\n\n（在场: ${s.scene.present_npcs.join("、") || "（无）"}）`,
      });
    }
    setHistory(turns);
  }

  async function handleNewSession() {
    const sess = await createSession("新冒险 " + new Date().toLocaleString());
    await refreshSessions();
    await openSession(sess.id);
  }

  async function handleDeleteSession(id: number) {
    if (!confirm("确认删除此存档？")) return;
    await deleteSession(id);
    if (activeId === id) {
      setActiveId(null);
      setState(null);
      setHistory([]);
    }
    await refreshSessions();
  }

  async function handleSubmit(text: string) {
    if (!activeId || !text.trim() || busy) return;
    setError(null);
    setBusy(true);
    const userText = text;
    setInput("");
    setLastOptions([]);
    // 立刻 push 玩家这一行，DM 暂时显示"DM 在叙述..."
    setHistory((prev) => [...prev, { user: userText, dm: "" }]);
    try {
      const resp: TurnResponse = await playTurn(activeId, userText);
      // 替换最后一条的 dm 为完整 narration，标 typing=true 触发打字机
      setHistory((prev) => {
        const copy = [...prev];
        copy[copy.length - 1] = { user: userText, dm: resp.narration, typing: true };
        return copy;
      });
      setState(resp.state);
      setLastOptions(resp.options);
      // 刷新右侧 sessions list 的 turn_count（带轻量刷新即可）
      refreshSessions().catch(() => {});
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "网络异常");
      // 删除我们刚刚加的"待回复"行
      setHistory((prev) => prev.slice(0, -1));
    } finally {
      setBusy(false);
    }
  }

  function handleLogout() {
    apiLogout();
    navigate("/auth");
  }

  return (
    <div className="h-full flex bg-stone-900 text-parchment">
      {/* 侧栏：存档列表 */}
      <aside className="w-60 border-r border-stone-800 flex flex-col">
        <div className="p-4 border-b border-stone-800">
          <button
            onClick={handleNewSession}
            className="w-full py-2 bg-amber-700 hover:bg-amber-600 rounded text-sm transition"
          >
            + 新建冒险
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {sessions.map((s) => (
            <div
              key={s.id}
              className={`group p-2 rounded cursor-pointer flex justify-between items-start ${
                s.id === activeId ? "bg-stone-800" : "hover:bg-stone-800/60"
              }`}
              onClick={() => openSession(s.id)}
            >
              <div className="flex-1 min-w-0">
                <div className="text-sm truncate">{s.title}</div>
                <div className="text-xs text-stone-500">
                  回合 {s.turn_count} · {s.location}
                </div>
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  handleDeleteSession(s.id);
                }}
                className="opacity-0 group-hover:opacity-100 text-stone-500 hover:text-red-400 text-xs ml-2"
                title="删除"
              >
                ✕
              </button>
            </div>
          ))}
          {sessions.length === 0 && (
            <div className="text-stone-500 text-xs text-center mt-8">
              还没有存档，点上方"新建冒险"开始
            </div>
          )}
        </div>
        <div className="p-3 border-t border-stone-800">
          <button
            onClick={handleLogout}
            className="w-full text-xs text-stone-500 hover:text-parchment transition"
          >
            退出登录
          </button>
        </div>
      </aside>

      {/* 主区：场景叙事流 */}
      <main className="flex-1 flex flex-col min-w-0">
        <div ref={scrollRef} className="flex-1 overflow-y-auto px-8 py-6 space-y-4 max-w-3xl mx-auto w-full">
          {history.map((turn, idx) => (
            <ChatBlock
              key={idx}
              turn={turn}
              isLast={idx === history.length - 1}
              onTypingDone={() => {
                // 打字结束后取消 typing 标志，避免再次触发
                setHistory((prev) => {
                  if (idx !== prev.length - 1) return prev;
                  const copy = [...prev];
                  copy[idx] = { ...copy[idx], typing: false };
                  return copy;
                });
              }}
            />
          ))}
          {busy && history[history.length - 1]?.dm === "" && (
            <div className="text-stone-500 italic text-sm">DM 正在叙述...</div>
          )}
        </div>

        {/* 输入区 */}
        <div className="border-t border-stone-800 p-4 max-w-3xl mx-auto w-full">
          {lastOptions.length > 0 && (
            <div className="flex flex-wrap gap-2 mb-2">
              {lastOptions.map((opt, i) => (
                <button
                  key={i}
                  onClick={() => setInput(opt)}
                  className="px-3 py-1 text-xs bg-stone-800 hover:bg-stone-700 border border-stone-700 rounded transition"
                  disabled={busy}
                >
                  {opt}
                </button>
              ))}
            </div>
          )}
          {error && (
            <div className="text-red-400 text-sm mb-2 bg-red-900/30 border border-red-800 rounded px-3 py-1">
              {error}
            </div>
          )}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSubmit(input);
            }}
            className="flex gap-2"
          >
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={activeId ? "输入你想做什么..." : "请先创建或选择一个存档"}
              disabled={busy || !activeId}
              className="flex-1 px-3 py-2 bg-stone-800 border border-stone-700 rounded focus:outline-none focus:border-amber-600 disabled:opacity-50"
            />
            <button
              type="submit"
              disabled={busy || !activeId || !input.trim()}
              className="px-4 py-2 bg-amber-700 hover:bg-amber-600 disabled:opacity-50 rounded transition"
            >
              {busy ? "..." : "发出行动"}
            </button>
          </form>
        </div>
      </main>

      {/* 右栏：玩家状态 */}
      <aside className="w-64 border-l border-stone-800 p-4 overflow-y-auto">
        {state && <PlayerPanel state={state} />}
      </aside>
    </div>
  );
}

// ===== 打字机渲染 =====
function ChatBlock({
  turn,
  isLast,
  onTypingDone,
}: {
  turn: ChatTurn;
  isLast: boolean;
  onTypingDone: () => void;
}) {
  const [shown, setShown] = useState(turn.typing ? "" : turn.dm);

  useEffect(() => {
    if (!turn.typing) {
      setShown(turn.dm);
      return;
    }
    setShown("");
    let i = 0;
    const id = setInterval(() => {
      i++;
      setShown(turn.dm.slice(0, i));
      if (i >= turn.dm.length) {
        clearInterval(id);
        onTypingDone();
      }
    }, 30);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [turn.dm, turn.typing]);

  return (
    <div className="space-y-2">
      {turn.user && (
        <div className="flex justify-end">
          <div className="bg-amber-800/30 border border-amber-900/50 rounded-lg px-3 py-2 max-w-[80%] text-sm">
            {turn.user}
          </div>
        </div>
      )}
      {turn.dm && (
        <div className="bg-stone-800/50 border border-stone-700 rounded-lg px-4 py-3 leading-relaxed">
          <span className={isLast && turn.typing ? "cursor-blink" : ""}>{shown}</span>
        </div>
      )}
    </div>
  );
}

// ===== 玩家状态面板 =====
function PlayerPanel({ state }: { state: GameState }) {
  const { player, scene } = state;
  return (
    <div className="space-y-4 text-sm">
      <Stat label="位置" value={scene.location} />
      <div className="space-y-1">
        <Bar label="HP" cur={player.hp} max={player.max_hp} color="bg-red-600" />
        <Bar label="MP" cur={player.mp} max={player.max_mp} color="bg-blue-600" />
      </div>
      <Stat label="金币" value={`${player.gold}`} />
      <Stat label="等级" value={`${player.level}`} />
      <Stat label="回合" value={`${state.turn_count}`} />

      <div>
        <div className="text-stone-500 text-xs mb-1">物品</div>
        <div className="text-xs">
          {player.inventory.length === 0 ? (
            <span className="text-stone-600">（空）</span>
          ) : (
            <ul className="space-y-1">
              {player.inventory.map((item, i) => (
                <li key={i} className="text-parchment">· {item}</li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <div>
        <div className="text-stone-500 text-xs mb-1">在场 NPC</div>
        <div className="text-xs">
          {scene.present_npcs.length === 0 ? (
            <span className="text-stone-600">（无）</span>
          ) : (
            <ul className="space-y-1">
              {scene.present_npcs.map((npc, i) => (
                <li key={i}>· {npc}</li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {state.long_term_summary && (
        <div>
          <div className="text-stone-500 text-xs mb-1">剧情摘要</div>
          <div className="text-xs text-stone-400 leading-relaxed bg-stone-800/50 rounded p-2">
            {state.long_term_summary}
          </div>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between items-baseline">
      <span className="text-stone-500 text-xs">{label}</span>
      <span className="text-parchment">{value}</span>
    </div>
  );
}

function Bar({ label, cur, max, color }: { label: string; cur: number; max: number; color: string }) {
  const pct = Math.max(0, Math.min(100, (cur / max) * 100));
  return (
    <div>
      <div className="flex justify-between text-xs mb-1">
        <span className="text-stone-500">{label}</span>
        <span className="text-parchment">{cur}/{max}</span>
      </div>
      <div className="h-2 bg-stone-800 rounded overflow-hidden">
        <div className={`h-full ${color} transition-all`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
