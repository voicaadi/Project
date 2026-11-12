import { useCallback, useEffect, useRef, useState } from "react";

import {

  Bot, LayoutDashboard, MessageSquare, Container, Terminal, FolderOpen,

  Activity, Settings, Send, Server, Cpu, ShieldCheck, CircleCheck,

  CircleAlert, LoaderCircle, RefreshCw, LogOut, Plus, Play, Square,

} from "lucide-react";

import { Terminal as XTerm } from "@xterm/xterm";

import { FitAddon } from "@xterm/addon-fit";

import "@xterm/xterm/css/xterm.css";

import "./App.css";

const API_URL = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");

function App() {

  const [backend, setBackend] = useState("Checking...");

  const [authMode, setAuthMode] = useState("login");

  const [loginEmail, setLoginEmail] = useState("");

  const [loginPassword, setLoginPassword] = useState("");

  const [registerUsername, setRegisterUsername] = useState("");

  const [accessToken, setAccessToken] = useState("");

  const [loggedInUser, setLoggedInUser] = useState(null);

  const [authLoading, setAuthLoading] = useState(false);

  const [authError, setAuthError] = useState("");

  const [workspaces, setWorkspaces] = useState([]);

  const [workspaceId, setWorkspaceId] = useState("");

  const [workspaceLoading, setWorkspaceLoading] = useState(false);

  const [workspaceError, setWorkspaceError] = useState("");

  const [newWorkspaceName, setNewWorkspaceName] = useState("My Linux Workspace");

  const [workspaceActionLoading, setWorkspaceActionLoading] = useState(false);

  const [messages, setMessages] = useState([{

    role: "assistant",

    content: "Hello! I'm Adrian AI Assistant, powered by Google Gemini. Select your workspace and ask me a DevOps question.",

  }]);

  const [message, setMessage] = useState("");

  const [chatLoading, setChatLoading] = useState(false);

  const [terminalConnection, setTerminalConnection] = useState("Disconnected");

  const [terminalError, setTerminalError] = useState("");

  const terminalSocketRef = useRef(null);

  const xtermHostRef = useRef(null);

  const xtermRef = useRef(null);

  const fitAddonRef = useRef(null);

  const selectedWorkspace = workspaces.find((w) => String(w.id) === String(workspaceId));

  const workspaceStatus = selectedWorkspace?.status || "not_created";

  const workspaceRunning = workspaceStatus === "running";

  const apiFetch = useCallback((path, options = {}) => {

    const headers = {

      ...(options.body ? { "Content-Type": "application/json" } : {}),

      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),

      ...options.headers,

    };

    return fetch(`${API_URL}${path}`, { ...options, headers });

  }, [accessToken]);

  useEffect(() => {

    fetch(`${API_URL}/health`)

      .then((r) => {

        if (!r.ok) throw new Error("Backend unavailable");

        return r.json();

      })

      .then(() => setBackend("Online"))

      .catch(() => setBackend("Offline"));

  }, []);

  const loadWorkspaces = useCallback(async (token = accessToken) => {

    if (!token) return;

    setWorkspaceLoading(true);

    setWorkspaceError("");

    try {

      const response = await fetch(`${API_URL}/api/workspaces/`, {

        headers: { Authorization: `Bearer ${token}` },

      });

      const data = await response.json();

      if (!response.ok) throw new Error(data.detail || "Could not load workspaces.");

      const list = Array.isArray(data) ? data : data.workspaces || [];

      setWorkspaces(list);

      setWorkspaceId((current) => {

        if (list.some((w) => String(w.id) === String(current))) return current;

        return list.length ? String(list[0].id) : "";

      });

    } catch (error) {

      setWorkspaceError(error.message || "Could not load workspaces.");

    } finally {

      setWorkspaceLoading(false);

    }

  }, [accessToken]);

  useEffect(() => {

    if (accessToken) loadWorkspaces(accessToken);

  }, [accessToken, loadWorkspaces]);

  async function authenticate(e) {

    e.preventDefault();

    if (authLoading) return;

    setAuthLoading(true);

    setAuthError("");

    try {

      const isRegister = authMode === "register";

      const endpoint = isRegister ? "/api/auth/register" : "/api/auth/login";

      const payload = isRegister

        ? { email: loginEmail.trim(), username: registerUsername.trim(), password: loginPassword }

        : { email: loginEmail.trim(), password: loginPassword };

      const response = await fetch(`${API_URL}${endpoint}`, {

        method: "POST",

        headers: { "Content-Type": "application/json" },

        body: JSON.stringify(payload),

      });

      const data = await response.json();

      if (!response.ok) throw new Error(data.detail || `${isRegister ? "Registration" : "Login"} failed.`);

      if (isRegister) {

        setAuthMode("login");

        setAuthError("");

        setLoginPassword("");

        alert("Account created. Please sign in.");

        return;

      }

      if (!data.access_token) throw new Error("Login response did not include an access token.");

      setAccessToken(data.access_token);

      setLoggedInUser(data.user || { email: loginEmail.trim() });

      setLoginPassword("");

      setMessages([{

        role: "assistant",

        content: `Welcome${data.user?.username ? `, ${data.user.username}` : ""}! Your personal workspace is ready when you select or create one.`,

      }]);

    } catch (error) {

      setAuthError(error.message || "Authentication failed.");

    } finally {

      setAuthLoading(false);

    }

  }

  function logout() {

    terminalSocketRef.current?.close(1000, "User logged out");

    terminalSocketRef.current = null;

    xtermRef.current?.dispose();

    xtermRef.current = null;

    setAccessToken("");

    setLoggedInUser(null);

    setWorkspaces([]);

    setWorkspaceId("");

    setMessages([{

      role: "assistant",

      content: "You have been logged out. Sign in to access your own workspace.",

    }]);

    setTerminalConnection("Disconnected");

    setTerminalError("");

    setWorkspaceError("");

    setLoginPassword("");

  }

  async function createWorkspace(e) {

    e.preventDefault();

    const name = newWorkspaceName.trim();

    if (!name || workspaceActionLoading) return;

    setWorkspaceActionLoading(true);

    setWorkspaceError("");

    try {

      const response = await apiFetch("/api/workspaces/", {

        method: "POST",

        body: JSON.stringify({ name }),

      });

      const data = await response.json();

      if (!response.ok) throw new Error(data.detail || "Could not create workspace.");

      await loadWorkspaces();

      if (data.id) setWorkspaceId(String(data.id));

    } catch (error) {

      setWorkspaceError(error.message);

    } finally {

      setWorkspaceActionLoading(false);

    }

  }

  async function changeWorkspaceState(action) {

    if (!workspaceId || workspaceActionLoading) return;

    setWorkspaceActionLoading(true);

    setWorkspaceError("");

    try {

      const response = await apiFetch(`/api/workspaces/${workspaceId}/${action}`, {

        method: "POST",

      });

      const data = await response.json();

      if (!response.ok) throw new Error(data.detail || `Could not ${action} workspace.`);

      await loadWorkspaces();

    } catch (error) {

      setWorkspaceError(error.message);

    } finally {

      setWorkspaceActionLoading(false);

    }

  }

  async function sendMessage(e) {

    e.preventDefault();

    const text = message.trim();

    if (!text || chatLoading) return;

    if (!accessToken || !workspaceId) {

      setMessages((prev) => [...prev, {

        role: "assistant",

        content: "Please create or select a workspace before chatting.",

      }]);

      return;

    }

    setMessages((prev) => [...prev, { role: "user", content: text }]);

    setMessage("");

    setChatLoading(true);

    try {

      const response = await apiFetch("/api/chat", {

        method: "POST",

        body: JSON.stringify({ message: text, workspace_id: Number(workspaceId) }),

      });

      const data = await response.json();

      if (!response.ok) throw new Error(data.detail || "AI request failed.");

      setMessages((prev) => [...prev, { role: "assistant", content: data.response }]);

    } catch (error) {

      setMessages((prev) => [...prev, {

        role: "assistant",

        content: `Error: ${error.message}`,

      }]);

    } finally {

      setChatLoading(false);

    }

  }

  // xterm.js is created only after authentication and is disposed on logout.

  useEffect(() => {

    if (!accessToken || !xtermHostRef.current || xtermRef.current) return undefined;

    const terminal = new XTerm({

      cursorBlink: true,

      convertEol: true,

      fontFamily: "Consolas, 'Courier New', monospace",

      fontSize: 13,

      lineHeight: 1.45,

      scrollback: 3000,

      theme: {

        background: "#171923",

        foreground: "#e8e8ee",

        cursor: "#7ee787",

        cursorAccent: "#171923",

        selectionBackground: "#514866",

      },

    });

    const fitAddon = new FitAddon();

    terminal.loadAddon(fitAddon);

    terminal.open(xtermHostRef.current);

    terminal.writeln("Adrian AI workspace terminal");

    terminal.writeln("Select a running workspace to connect.");

    xtermRef.current = terminal;

    fitAddonRef.current = fitAddon;

    requestAnimationFrame(() => {

      try { fitAddon.fit(); } catch { /* terminal may not be visible yet */ }

    });

    const resizeObserver = new ResizeObserver(() => {

      try { fitAddon.fit(); } catch { /* ignore transient layout changes */ }

    });

    resizeObserver.observe(xtermHostRef.current);

    const inputSubscription = terminal.onData((data) => {

      const socket = terminalSocketRef.current;

      if (socket?.readyState === WebSocket.OPEN) socket.send(data);

    });

    const resizeSubscription = terminal.onResize(({ cols, rows }) => {

      const socket = terminalSocketRef.current;

      if (socket?.readyState === WebSocket.OPEN) socket.send(`\x00RESIZE:${cols}:${rows}`);

    });

    return () => {

      inputSubscription.dispose();

      resizeSubscription.dispose();

      resizeObserver.disconnect();

      terminal.dispose();

      xtermRef.current = null;

      fitAddonRef.current = null;

    };

  }, [accessToken, workspaceId, workspaceRunning]);

  // A WebSocket is opened only for the selected workspace and authenticated token.

  useEffect(() => {

    if (!accessToken || !workspaceId || !workspaceRunning) {

      terminalSocketRef.current?.close(1000, "Workspace unavailable");

      terminalSocketRef.current = null;

      setTerminalConnection("Disconnected");

      return undefined;

    }

    let cancelled = false;

    setTerminalError("");

    const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";

    const socket = new WebSocket(

      `${wsProtocol}//${window.location.host}/api/workspaces/${encodeURIComponent(workspaceId)}/terminal/ws`

    );

    terminalSocketRef.current = socket;

    setTerminalConnection("Connecting");

    socket.onopen = () => {

      if (cancelled) return;

      socket.send(JSON.stringify({ token: accessToken }));

      setTerminalConnection("Connected");

      xtermRef.current?.focus();

      const fitAddon = fitAddonRef.current;

      try { fitAddon?.fit(); } catch { /* ignore */ }

    };

    socket.onmessage = (event) => {

      if (!cancelled) xtermRef.current?.write(event.data);

    };

    socket.onerror = () => {

      if (!cancelled) {

        setTerminalConnection("Error");

        setTerminalError("Terminal connection failed.");

      }

    };

    socket.onclose = (event) => {

      if (cancelled) return;

      setTerminalConnection("Disconnected");

      if (event.code === 4401) setTerminalError("Session expired. Please sign in again.");

      else if (event.code === 4403) setTerminalError("You do not own this workspace.");

      else if (event.code === 4409) setTerminalError("Workspace container is not running.");

      else if (event.code !== 1000) setTerminalError("Terminal connection closed.");

    };

    return () => {

      cancelled = true;

      if (socket.readyState < WebSocket.CLOSING) socket.close(1000, "Workspace changed");

      if (terminalSocketRef.current === socket) terminalSocketRef.current = null;

    };

  }, [accessToken, workspaceId, workspaceRunning]);

  const runningCount = workspaces.filter((w) => w.status === "running").length;

  if (!accessToken) {

    return (

      <main className="adrian-login-page">

        <style>{`

          .adrian-login-page{position:relative;isolation:isolate;min-height:100vh;display:grid;place-items:center;overflow:hidden;padding:32px 20px;background:#b8eee8;color:#302642}
          .adrian-login-card{position:relative;z-index:2;width:min(100%,460px);box-sizing:border-box;padding:38px;background:#fff4d9;border:2px solid #40334d;box-shadow:8px 8px 0 #40334d}
          .adrian-login-brand{display:flex;flex-direction:column;align-items:center;gap:11px;text-align:center}
          .adrian-login-icon{width:58px;height:58px;display:grid;place-items:center;background:#f2a8c9;border:2px solid #40334d;box-shadow:4px 4px 0 #40334d}
          .adrian-login-brand h1{margin:0;color:#08060d;font-size:29px;letter-spacing:1.2px;line-height:1.1}
          .adrian-login-brand h1 span{color:#08060d}
          .adrian-login-brand p{margin:5px 0 0;color:#302642;font-size:10px;letter-spacing:1.6px;font-weight:900}
          .adrian-login-kicker{font-size:10px;letter-spacing:1.4px;font-weight:800}
          .adrian-login-intro{margin:32px 0 24px;text-align:center}
          .adrian-login-intro h2{font-size:32px;margin:12px 0 8px;color:#08060d}
          .adrian-login-intro p{font-size:14px;line-height:1.6;color:#665b72}
          .adrian-login-form{display:grid;gap:11px}
          .adrian-login-form label{margin-top:8px;font-size:10px;font-weight:800;letter-spacing:1px}
          .adrian-login-form input{box-sizing:border-box;width:100%;padding:14px;background:#fffdf6;border:1.5px solid #8d7895;color:#302642;font:inherit}
          .adrian-login-form button{margin-top:14px;min-height:48px;display:flex;justify-content:center;align-items:center;gap:9px;border:2px solid #40334d;background:#f2a8c9;color:#302642;font-weight:800;cursor:pointer}
          .adrian-login-form button:disabled{opacity:.65;cursor:wait}
          .adrian-login-error{color:#b42342;font-size:13px}
          .adrian-login-footer{display:flex;justify-content:space-between;gap:10px;margin-top:26px;padding-top:15px;border-top:1px dashed #b79aae;color:#796b80;font-size:9px;font-weight:700;letter-spacing:.7px}
          .adrian-auth-switch{border:0;background:transparent;color:#8e3763;text-decoration:underline;cursor:pointer;padding:12px}
          .adrian-sticker-layer{position:absolute;inset:0;z-index:1;pointer-events:none}
          .adrian-sticker{position:absolute;z-index:1;display:flex;align-items:center;gap:7px;min-width:112px;padding:9px 11px;border:2px solid #40334d;border-radius:3px;background:#fff4d9;color:#302642;box-shadow:4px 4px 0 #40334d;font:900 10px/1.1 system-ui,sans-serif;letter-spacing:.7px;animation:adrian-float 5.2s ease-in-out infinite;user-select:none;pointer-events:none}
          .adrian-sticker-icon{display:grid;place-items:center;width:25px;height:25px;flex:0 0 25px;border:1px solid #40334d;background:#f2a8c9;font-size:14px}
          .adrian-sticker small{display:block;margin-top:3px;font-size:7px;letter-spacing:.6px;opacity:.72}
          .sticker-terraform{top:12%;left:3%;transform:rotate(-8deg);background:#e7defb;animation-delay:-.7s}
          .sticker-docker{top:17%;right:3%;transform:rotate(7deg);background:#d9f3f0;animation-delay:-2.1s}
          .sticker-kubernetes{top:39%;left:2%;transform:rotate(6deg);background:#e7defb;animation-delay:-1.4s}
          .sticker-linux{top:44%;right:2%;transform:rotate(-7deg);background:#fff0d0;animation-delay:-3s}
          .sticker-aws{bottom:23%;left:3%;transform:rotate(-6deg);background:#fff0d0;animation-delay:-2.5s}
          .sticker-github{bottom:18%;right:3%;transform:rotate(7deg);background:#f9dce9;animation-delay:-1s}
          .sticker-ansible{bottom:5%;left:16%;transform:rotate(5deg);background:#f9dce9;animation-delay:-3.5s}
          .sticker-cicd{bottom:5%;right:16%;transform:rotate(-5deg);background:#d9f3f0;animation-delay:-.4s}
          .sticker-grafana{top:5%;left:39%;transform:rotate(-4deg);background:#fff0d0;animation-delay:-2.8s}
          .sticker-prometheus{top:5%;right:35%;transform:rotate(5deg);background:#f9dce9;animation-delay:-1.8s}
          @keyframes adrian-float{0%,100%{translate:0 0}50%{translate:0 -11px}}
          @media(max-width:900px){.adrian-sticker{min-width:0;padding:7px;font-size:8px}.adrian-sticker small{display:none}.sticker-grafana{left:3%;top:4%}.sticker-prometheus{right:3%;top:4%}.sticker-ansible{left:3%;bottom:3%}.sticker-cicd{right:3%;bottom:3%}}
          @media(max-width:620px){.adrian-sticker{display:none}.adrian-login-page{padding:18px 12px;overflow:auto}.adrian-login-card{padding:28px 22px}.adrian-login-footer{flex-direction:column}.adrian-login-intro{margin:27px 0 20px}}
          @media(prefers-reduced-motion:reduce){.adrian-sticker{animation:none}}
        `}</style>

        <div className="adrian-sticker-layer" aria-hidden="true">
          <div className="adrian-sticker sticker-grafana"><span className="adrian-sticker-icon">◉</span><span>GRAFANA<small>OBSERVABILITY</small></span></div>
          <div className="adrian-sticker sticker-prometheus"><span className="adrian-sticker-icon">🔥</span><span>PROMETHEUS<small>METRICS</small></span></div>
          <div className="adrian-sticker sticker-terraform"><span className="adrian-sticker-icon">⌘</span><span>TERRAFORM<small>INFRASTRUCTURE</small></span></div>
          <div className="adrian-sticker sticker-docker"><span className="adrian-sticker-icon">🐳</span><span>DOCKER<small>CONTAINERS</small></span></div>
          <div className="adrian-sticker sticker-kubernetes"><span className="adrian-sticker-icon">☸</span><span>KUBERNETES<small>ORCHESTRATION</small></span></div>
          <div className="adrian-sticker sticker-linux"><span className="adrian-sticker-icon">🐧</span><span>LINUX<small>COMMAND LINE</small></span></div>
          <div className="adrian-sticker sticker-aws"><span className="adrian-sticker-icon">☁</span><span>AWS<small>CLOUD</small></span></div>
          <div className="adrian-sticker sticker-github"><span className="adrian-sticker-icon">⌂</span><span>GITHUB<small>SOURCE CONTROL</small></span></div>
          <div className="adrian-sticker sticker-ansible"><span className="adrian-sticker-icon">✣</span><span>ANSIBLE<small>AUTOMATION</small></span></div>
          <div className="adrian-sticker sticker-cicd"><span className="adrian-sticker-icon">⇄</span><span>CI / CD<small>PIPELINES</small></span></div>

        </div>

        <section className="adrian-login-card">

          <div className="adrian-login-brand">
            <div className="adrian-login-icon"><Bot size={32} /></div>
            <div><h1>ADRIAN <span>AI</span></h1><p>DEVOPS ASSISTANT CONSOLE</p></div>
          </div>
          <div className="adrian-login-intro">

            <span className="adrian-login-kicker">YOUR DEVOPS COMMAND CENTER</span>

            <h2>{authMode === "login" ? "Welcome back." : "Create account."}</h2>

            <p>Sign in or register to access your own dashboard, AI assistant and isolated Ubuntu workspace.</p>

          </div>

          <form className="adrian-login-form" onSubmit={authenticate}>

            {authMode === "register" && <>

              <label htmlFor="adrian-username">USERNAME</label>

              <input id="adrian-username" value={registerUsername} onChange={(e) => setRegisterUsername(e.target.value)} minLength={3} maxLength={100} autoComplete="username" required placeholder="Choose a username" />

            </>}

            <label htmlFor="adrian-email">EMAIL ADDRESS</label>

            <input id="adrian-email" type="email" value={loginEmail} onChange={(e) => setLoginEmail(e.target.value)} autoComplete="email" required placeholder="you@example.com" />

            <label htmlFor="adrian-password">PASSWORD</label>

            <input id="adrian-password" type="password" value={loginPassword} onChange={(e) => setLoginPassword(e.target.value)} minLength={authMode === "register" ? 8 : undefined} autoComplete={authMode === "login" ? "current-password" : "new-password"} required placeholder="Enter your password" />

            {authError && <p className="adrian-login-error">{authError}</p>}

            <button type="submit" disabled={authLoading}>

              {authLoading ? <LoaderCircle size={17} className="spin" /> : <ShieldCheck size={17} />}

              {authLoading ? "PLEASE WAIT..." : authMode === "login" ? "SIGN IN TO ADRIAN AI" : "CREATE ACCOUNT"}

            </button>

          </form>

          <button className="adrian-auth-switch" type="button" onClick={() => { setAuthMode(authMode === "login" ? "register" : "login"); setAuthError(""); }}>

            {authMode === "login" ? "New here? Create an account" : "Already registered? Sign in"}

          </button>

          <div className="adrian-login-footer"><span>API: {backend}</span><span>PRIVATE WORKSPACE ACCESS</span></div>

        </section>

      </main>

    );

  }

  return (

    <div className="app-shell">

      <aside className="sidebar">

        <div className="brand">

          <div className="brand-icon"><Bot size={25} /></div>

          <div><h1>ADRIAN<span> AI</span></h1><p>ASSISTANT CONSOLE</p></div>

        </div>

        <div className="sidebar-label">WORKSPACE</div>

        <nav className="nav-menu">

          <a className="nav-item active" href="#dashboard"><LayoutDashboard size={18} /> Dashboard</a>

          <a className="nav-item" href="#assistant"><MessageSquare size={18} /> AI Assistant</a>

          <a className="nav-item" href="#containers"><Container size={18} /> My Workspaces</a>

          <a className="nav-item" href="#terminal"><Terminal size={18} /> Terminal</a>

          <a className="nav-item" href="#settings"><Settings size={18} /> Settings</a>

        </nav>

        <div className="sidebar-bottom">

          <div className="sidebar-status">

            <span className={`status-dot ${backend === "Online" ? "online" : ""}`} />

            <div><strong>API CONNECTION</strong><small>{backend}</small></div>

          </div>

          <p className="sidebar-version">ADRIAN AI · VERSION 1.0.0</p>

        </div>

      </aside>

      <main className="main-content" id="dashboard">

        <header className="topbar">

          <div><p className="eyebrow">YOUR COMMAND CENTER</p><h2>Dashboard</h2></div>

          <div className="topbar-right">

            <span className="date-label">{loggedInUser?.email || loggedInUser?.username}</span>

            <button type="button" className="refresh-button" onClick={logout}><LogOut size={15} /> Log out</button>

          </div>

        </header>

        <section className="welcome-banner">

          <div><p className="banner-kicker">PRIVATE USER SESSION</p><h3>Welcome to your DevOps workspace!</h3><p>Your dashboard displays only workspaces belonging to your account.</p></div>

          <div className="banner-art"><Server size={62} strokeWidth={1.3} /></div>

        </section>

        <section className="stats-grid" aria-label="Account overview">

          <article className="stat-card"><div className="stat-icon pink"><Server size={20} /></div><div className="stat-copy"><span>BACKEND API</span><strong>{backend}</strong><small>Service status</small></div></article>

          <article className="stat-card"><div className="stat-icon teal"><FolderOpen size={20} /></div><div className="stat-copy"><span>MY WORKSPACES</span><strong>{workspaces.length}</strong><small>Owned by your account</small></div></article>

          <article className="stat-card"><div className="stat-icon purple"><Activity size={20} /></div><div className="stat-copy"><span>RUNNING WORKSPACES</span><strong>{runningCount}</strong><small>Your active workspaces</small></div></article>

          <article className="stat-card"><div className="stat-icon yellow"><ShieldCheck size={20} /></div><div className="stat-copy"><span>AI ASSISTANT</span><strong>Gemini</strong><small>AI service configured</small></div></article>

        </section>

        <section className="panel docker-panel" id="containers">

          <div className="panel-header">

            <div className="panel-title"><div className="panel-icon"><FolderOpen size={19} /></div><div><h3>My Linux Workspaces</h3><p>Only workspaces owned by your account</p></div></div>

            <button className="refresh-button" type="button" onClick={() => loadWorkspaces()} disabled={workspaceLoading}><RefreshCw size={15} className={workspaceLoading ? "spin" : ""} /> Refresh</button>

          </div>

          <form className="terminal-controls" onSubmit={createWorkspace}>

            <label>NEW WORKSPACE NAME<input value={newWorkspaceName} onChange={(e) => setNewWorkspaceName(e.target.value)} maxLength={100} required /></label>

            <button className="terminal-run-button" type="submit" disabled={workspaceActionLoading}><Plus size={15} /> Create workspace</button>

          </form>

          {workspaceError && <div className="docker-message docker-error"><CircleAlert size={18} /><p>{workspaceError}</p></div>}

          {workspaceLoading ? <div className="docker-message"><LoaderCircle className="spin" /> Loading your workspaces...</div> :

            workspaces.length === 0 ? <div className="docker-message empty-state"><FolderOpen size={22} /><div><strong>No workspaces yet</strong><p>Create your first Linux workspace above.</p></div></div> :

            <div className="container-list">

              {workspaces.map((workspace) => (

                <article className="container-row" key={workspace.id} onClick={() => setWorkspaceId(String(workspace.id))} style={{ cursor: "pointer", outline: String(workspace.id) === String(workspaceId) ? "2px solid #8b75c9" : "none" }}>

                  <div className="container-symbol"><Container size={19} /></div>

                  <div className="container-main"><strong>{workspace.name}</strong><small>Workspace ID: {workspace.id}</small></div>

                  <div className="container-meta"><span className={`container-status ${workspace.status === "running" ? "running" : "stopped"}`}><span /> {workspace.status}</span></div>

                </article>

              ))}

            </div>

          }

          {selectedWorkspace && <div className="panel-footer">

            <span>Selected: {selectedWorkspace.name}</span>

            <span>{workspaceRunning ? "Workspace running" : "Workspace stopped"}</span>

            <button className="refresh-button" type="button" disabled={workspaceActionLoading} onClick={() => changeWorkspaceState(workspaceRunning ? "stop" : "start")}>

              {workspaceActionLoading ? <LoaderCircle size={14} className="spin" /> : workspaceRunning ? <Square size={14} /> : <Play size={14} />}

              {workspaceRunning ? "Stop" : "Start"}

            </button>

          </div>}

        </section>

        <section className="panel terminal-panel" id="terminal">

          <div className="panel-header">

            <div className="panel-title"><div className="panel-icon terminal-icon"><Terminal size={19} /></div><div><h3>Ubuntu Terminal</h3><p>Your selected isolated workspace</p></div></div>

            <span className="terminal-readonly">{terminalConnection}</span>

          </div>

          {!workspaceId ? <div className="docker-message">Create or select a workspace to use the terminal.</div> :

            !workspaceRunning ? <div className="docker-message">Start the selected workspace to connect to its terminal.</div> :

            <>

              {terminalError && <p className="terminal-disclaimer has-error">{terminalError}</p>}

              <div className="terminal-window" style={{ background: "#171923", border: "1px solid #454052", overflow: "hidden" }}>

                <div className="terminal-window-bar"><span><i /><i /><i /></span><strong>ADRIAN AI / CLI</strong><span>{terminalConnection}</span></div>

                <div ref={xtermHostRef} style={{ height: 340, padding: "12px 14px", background: "#171923", boxSizing: "border-box" }} />

              </div>

            </>

          }

        </section>

        <div className="content-grid">

          <section className="panel chat-panel" id="assistant">

            <div className="panel-header"><div className="panel-title"><div className="panel-icon chat-icon"><Bot size={19} /></div><div><h3>AI Assistant</h3><p>Powered by Google Gemini · Your session</p></div></div><span className="live-pill">LIVE</span></div>

            <div className="chat-messages">

              {messages.map((item, index) => <div className={`chat-message ${item.role}`} key={`${item.role}-${index}`}><div className="message-avatar">{item.role === "assistant" ? <Bot size={16} /> : <span>YOU</span>}</div><div className="message-bubble"><small>{item.role === "assistant" ? "ADRIAN AI" : "YOU"}</small><p>{item.content}</p></div></div>)}

              {chatLoading && <div className="chat-message assistant"><div className="message-avatar"><Bot size={16} /></div><div className="message-bubble"><small>ADRIAN AI</small><p className="thinking"><LoaderCircle size={15} className="spin" /> Thinking...</p></div></div>}

            </div>

            <form className="chat-form" onSubmit={sendMessage}>

              <input type="text" value={message} onChange={(e) => setMessage(e.target.value)} placeholder={workspaceId ? "Ask about Docker, Linux, AWS, Kubernetes..." : "Select a workspace first..."} aria-label="Message Adrian AI" maxLength={4000} />

              <button type="submit" disabled={chatLoading || !message.trim() || !workspaceId}><Send size={18} /></button>

            </form>

            <p className="chat-hint">ENTER TO SEND · AI-GENERATED ANSWERS MAY NEED VERIFICATION</p>

          </section>

          <section className="panel health-panel" id="settings">

            <div className="panel-header"><div className="panel-title"><div className="panel-icon health-icon"><Activity size={19} /></div><div><h3>Account Health</h3><p>Service connection overview</p></div></div></div>

            <div className="health-list">

              <div className="health-item"><div className="health-item-icon"><Server size={17} /></div><div><strong>FastAPI Backend</strong><small>Same-origin API</small></div><span className={`health-state ${backend === "Online" ? "ok" : "fail"}`}>{backend === "Online" ? <CircleCheck size={16} /> : <CircleAlert size={16} />}{backend}</span></div>

              <div className="health-item"><div className="health-item-icon"><FolderOpen size={17} /></div><div><strong>Personal Workspaces</strong><small>Account-scoped API</small></div><span className="health-state ok"><CircleCheck size={16} /> Connected</span></div>

              <div className="health-item"><div className="health-item-icon"><Cpu size={17} /></div><div><strong>Gemini AI</strong><small>AI response service</small></div><span className="health-state ok"><CircleCheck size={16} /> Configured</span></div>

            </div>

            <div className="health-note"><ShieldCheck size={17} /><span>Workspace access is checked by the backend using your authenticated account.</span></div>

            <a className="docs-link" href={`${API_URL}/docs`} target="_blank" rel="noreferrer">Open API documentation</a>

          </section>

        </div>

        <footer className="page-footer"><span>BUILT FOR YOUR DEVOPS WORKFLOW</span><span>ADRIAN AI ASSISTANT · 2026</span></footer>

      </main>

    </div>

  );

}

export default App;
