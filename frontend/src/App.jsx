import { useEffect, useRef, useState } from "react";
import {
  Bot,
  LayoutDashboard,
  MessageSquare,
  Container,
  Terminal,
  FolderOpen,
  Activity,
  Settings,
  Send,
  Server,
  Cpu,
  HardDrive,
  ShieldCheck,
  CircleCheck,
  CircleAlert,
  ChevronRight,
  LoaderCircle,
  RefreshCw,
} from "lucide-react";
import { Terminal as XTerm } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import "@xterm/xterm/css/xterm.css";
import "./App.css";
const API_URL = "";
function App() {
  const [backend, setBackend] = useState("Checking...");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      content:
        "Hello! I'm Adrian AI Assistant, powered by Google Gemini. How can I help you today?",
    },
  ]);
  const [containers, setContainers] = useState([]);
  const [dockerLoading, setDockerLoading] = useState(false);
  const [dockerError, setDockerError] = useState("");
  const [dockerOnline, setDockerOnline] = useState(false);
  const [loginEmail, setLoginEmail] = useState("");
  const [loginPassword, setLoginPassword] = useState("");
  const [authMode, setAuthMode] = useState("login");
  const [registerUsername, setRegisterUsername] = useState("");
  const [registerPassword, setRegisterPassword] = useState("");
  const [registerConfirmPassword, setRegisterConfirmPassword] = useState("");
  const [accessToken, setAccessToken] = useState("");
  const [loggedInUser, setLoggedInUser] = useState(null);
  const [loginError, setLoginError] = useState("");
  const [workspaceId, setWorkspaceId] = useState("1");
  const [terminalCommand, setTerminalCommand] = useState("");
  const [terminalOutput, setTerminalOutput] = useState("Log in, then enter a Linux command.");
  const [terminalLoading, setTerminalLoading] = useState(false);
  const [terminalError, setTerminalError] = useState("");
  const terminalInputRef = useRef(null);
  const terminalOutputRef = useRef(null);
  const terminalSocketRef = useRef(null);
  const xtermHostRef = useRef(null);
  const xtermRef = useRef(null);
  const [terminalConnection, setTerminalConnection] = useState("Disconnected");
  useEffect(() => {
    fetch(`${API_URL}/health`)
      .then((response) => {
        if (!response.ok) throw new Error("Backend unavailable");
        return response.json();
      })
      .then(() => setBackend("Online"))
      .catch(() => setBackend("Offline"));
  }, []);
  async function loadContainers() {
    setDockerLoading(true);
    setDockerError("");
    try {
      const response = await fetch(`${API_URL}/api/docker/containers`);
      if (!response.ok) {
        throw new Error(`Docker request failed (${response.status})`);
      }
      const data = await response.json();
      setContainers(data.containers || []);
      setDockerOnline(true);
    } catch (error) {
      setDockerOnline(false);
      setDockerError(error.message || "Could not load Docker containers");
    } finally {
      setDockerLoading(false);
    }
  }
  useEffect(() => {
    loadContainers();
  }, []);
  async function sendMessage(e) {
    e.preventDefault();
    const userMessage = message.trim();
    if (!userMessage || loading) return;
    setMessages((prev) => [...prev, { role: "user", content: userMessage }]);
    setMessage("");
    setLoading(true);
    try {
      const response = await fetch(`${API_URL}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: userMessage }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "AI request failed");
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.response },
      ]);
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `Error: ${error.message}` },
      ]);
    } finally {
      setLoading(false);
    }
  }
  async function loginToTerminal(e) {
    e.preventDefault();
    setLoginError("");
    try {
      const response = await fetch(`${API_URL}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: loginEmail, password: loginPassword }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Login failed");
      setAccessToken(data.access_token);
      setLoggedInUser(data.user || { email: loginEmail });
      setLoginPassword("");
      setTerminalOutput("");
    } catch (error) {
      setLoginError(error.message || "Could not log in.");
    }
  }
  async function registerAccount(e) {
    e.preventDefault();
    setLoginError("");

    if (registerPassword.length < 8) {
      setLoginError("Password must contain at least 8 characters.");
      return;
    }
    if (registerPassword !== registerConfirmPassword) {
      setLoginError("Passwords do not match.");
      return;
    }

    setLoading(true);
    try {
      const response = await fetch(`${API_URL}/api/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: loginEmail,
          username: registerUsername,
          password: registerPassword,
        }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Registration failed.");

      setLoginPassword(registerPassword);
      setRegisterPassword("");
      setRegisterConfirmPassword("");
      setAuthMode("login");
      setLoginError("Account created successfully! You can now log in.");
    } catch (error) {
      setLoginError(error.message || "Could not create account.");
    } finally {
      setLoading(false);
    }
  }

  function runTerminalCommand(e) {
    e.preventDefault();
    const command = terminalCommand;
    if (!command.trim() || terminalLoading) return;
    const socket = terminalSocketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      setTerminalError("Terminal is not connected. Wait for the connection or sign in again.");
      return;
    }
    // A PTY echoes the typed command and returns its output in the same stream.
    // Send only the command plus Enter; do not add a second copy to the transcript.
    socket.send(command + "\n");
    setTerminalCommand("");
    setTerminalError("");
    terminalInputRef.current?.focus();
  }
  useEffect(() => {
    // The terminal host is rendered only after login. Initialize xterm
    // when accessToken becomes available, not only on the first app render.
    if (!accessToken || !xtermHostRef.current || xtermRef.current) return;
    const terminal = new XTerm({
      cursorBlink: true,
      convertEol: true,
      fontFamily: "Consolas, 'Courier New', monospace",
      fontSize: 13,
      lineHeight: 1.45,
      theme: {
        background: "#171923", foreground: "#e8e8ee",
        cursor: "#7ee787", cursorAccent: "#171923",
        selectionBackground: "#514866",
        black: "#171923", green: "#7ee787", brightGreen: "#7ee787",
      },
      scrollback: 3000,
    });
    const fitAddon = new FitAddon();
    terminal.loadAddon(fitAddon);
    terminal.open(xtermHostRef.current);
    fitAddon.fit();
    xtermRef.current = terminal;
    // xterm.js captures keyboard input only while its hidden textarea is focused.
    requestAnimationFrame(() => {
      terminal.focus();
      fitAddon.fit();
    });
    const resizeSubscription = terminal.onResize(({ cols, rows }) => {
  const socket = terminalSocketRef.current;
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(`\x00RESIZE:${cols}:${rows}`);
  }
});
    const inputSubscription = terminal.onData((data) => {
      const socket = terminalSocketRef.current;
      if (socket && socket.readyState === WebSocket.OPEN) socket.send(data);
    });
    const resizeObserver = new ResizeObserver(() => {
      try {
        fitAddon.fit();
      } catch (error) {
        console.error("Terminal resize failed:", error);
      }
    });
    resizeObserver.observe(xtermHostRef.current);

    return () => {
      inputSubscription.dispose();
      resizeSubscription.dispose();
      resizeObserver.disconnect();
      terminal.dispose();
      xtermRef.current = null;
    };
  }, [accessToken]);
  useEffect(() => {
    if (!accessToken || !workspaceId) {
      setTerminalConnection("Disconnected");
      return;
    }
    let socket;
    let cancelled = false;
    try {
      const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const wsHost = window.location.host;
      socket = new WebSocket(
        `${wsProtocol}//${wsHost}/api/workspaces/${encodeURIComponent(workspaceId)}/terminal/ws`
      );
      terminalSocketRef.current = socket;
      setTerminalConnection("Connecting");
      xtermRef.current?.reset();
      setTerminalError("");
      socket.onopen = () => {
        if (cancelled) return;
        socket.send(JSON.stringify({ token: accessToken }));
        setTerminalConnection("Connected");
        xtermRef.current?.focus();
      };
      socket.onmessage = (event) => {
        if (cancelled) return;
        xtermRef.current?.write(event.data);
      };
      socket.onerror = () => {
        if (!cancelled) {
          setTerminalConnection("Error");
          setTerminalError("WebSocket connection failed.");
        }
      };
      socket.onclose = (event) => {
        if (cancelled) return;
        setTerminalConnection("Disconnected");
        if (event.code === 4401) {
          setTerminalError("Session expired. Please log in again.");
          setAccessToken("");
          setLoggedInUser(null);
        } else if (event.code === 4403) {
          setTerminalError("You do not have access to this workspace.");
        } else if (event.code === 4409) {
          setTerminalError("Your Ubuntu workspace is not running. Start it first.");
        } else if (event.code !== 1000) {
          setTerminalError("Terminal connection closed.");
        }
      };
    } catch (error) {
      setTerminalConnection("Error");
      setTerminalError(error.message || "Could not open terminal connection.");
    }
    return () => {
      cancelled = true;
      if (socket && socket.readyState < WebSocket.CLOSING) {
        socket.close(1000, "Workspace changed or component unmounted");
      }
      if (terminalSocketRef.current === socket) {
        terminalSocketRef.current = null;
      }
    };
  }, [accessToken, workspaceId]);
  useEffect(() => {
    if (accessToken && terminalConnection === "Connected") {
      terminalInputRef.current?.focus();
    }
  }, [accessToken, terminalConnection]);
  const runningCount = containers.filter(
    (container) => container.status === "running"
  ).length;
  function formatPorts(ports) {
    if (!ports || Object.keys(ports).length === 0) return "No published ports";
    return Object.entries(ports)
      .map(([containerPort, bindings]) => {
        if (!bindings || bindings.length === 0) return containerPort;
        return bindings
          .map((binding) => `${binding.HostIp}:${binding.HostPort} → ${containerPort}`)
          .join(", ");
      })
      .join(" · ");
  }

  if (!accessToken) {
    return (
      <main className="adrian-login-page">
        <div className="adrian-logo-field" aria-hidden="true">
          {/* Left outer column */}
          <img className="adrian-logo" src="https://cdn.simpleicons.org/docker/2496ED" alt="" style={{"--x":"2.5%","--y":"7%","--w":"clamp(68px,8vw,118px)"}} />
          <img className="adrian-logo" src="https://cdn.simpleicons.org/grafana/F46800" alt="" style={{"--x":"2.5%","--y":"31%","--w":"clamp(68px,8vw,118px)"}} />
          <img className="adrian-logo" src="https://cdn.simpleicons.org/amazonaws/232F3E" alt="" style={{"--x":"2.5%","--y":"56%","--w":"clamp(72px,8.5vw,124px)"}} />
          <img className="adrian-logo" src="https://cdn.simpleicons.org/awslambda/FF9900" alt="" style={{"--x":"2.5%","--y":"70%","--w":"clamp(58px,6.5vw,92px)"}} />
          <img className="adrian-logo" src="https://cdn.simpleicons.org/nginx/009639" alt="" style={{"--x":"2.5%","--y":"81%","--w":"clamp(68px,8vw,118px)"}} />
          {/* Left inner column */}
          <img className="adrian-logo" src="https://cdn.simpleicons.org/jenkins/D24939" alt="" style={{"--x":"16%","--y":"7%","--w":"clamp(62px,7vw,104px)"}} />
          <img className="adrian-logo" src="https://cdn.simpleicons.org/terraform/7B42BC" alt="" style={{"--x":"16%","--y":"38%","--w":"clamp(62px,7vw,104px)"}} />
          <img className="adrian-logo" src="https://cdn.simpleicons.org/gitlab/FC6D26" alt="" style={{"--x":"16%","--y":"21%","--w":"clamp(62px,7vw,104px)"}} />
          <img className="adrian-logo" src="https://cdn.simpleicons.org/prometheus/E6522C" alt="" style={{"--x":"16%","--y":"70%","--w":"clamp(62px,7vw,104px)"}} />
          {/* Right inner column */}
          <img className="adrian-logo" src="https://cdn.simpleicons.org/ansible/EE0000" alt="" style={{"--x":"76%","--y":"7%","--w":"clamp(62px,7vw,104px)"}} />
          <img className="adrian-logo" src="https://cdn.simpleicons.org/helm/0F1689" alt="" style={{"--x":"76%","--y":"31%","--w":"clamp(62px,7vw,104px)"}} />
          <img className="adrian-logo" src="https://cdn.simpleicons.org/githubactions/2088FF" alt="" style={{"--x":"76%","--y":"56%","--w":"clamp(62px,7vw,104px)"}} />
          <img className="adrian-logo" src="https://cdn.simpleicons.org/hashicorp/000000" alt="" style={{"--x":"76%","--y":"81%","--w":"clamp(62px,7vw,104px)"}} />
          {/* Right outer column */}
          <img className="adrian-logo" src="https://cdn.simpleicons.org/kubernetes/326CE5" alt="" style={{"--x":"89%","--y":"7%","--w":"clamp(68px,8vw,118px)"}} />
          <img className="adrian-logo" src="https://upload.wikimedia.org/wikipedia/commons/3/35/Tux.svg" alt="" style={{"--x":"89%","--y":"31%","--w":"clamp(68px,8vw,118px)"}} />
          <img className="adrian-logo" src="https://cdn.simpleicons.org/github/181717" alt="" style={{"--x":"89%","--y":"56%","--w":"clamp(68px,8vw,118px)"}} />
          <img className="adrian-logo" src="https://cdn.simpleicons.org/argocd/EF7B4D" alt="" style={{"--x":"89%","--y":"81%","--w":"clamp(68px,8vw,118px)"}} />
          <img className="adrian-logo" src="https://cdn.simpleicons.org/microsoftazure/0078D4" alt="" style={{"--x":"89%","--y":"70%","--w":"clamp(58px,6.5vw,92px)"}} />
        </div>
        <style>{`
          .adrian-login-page{position:relative;isolation:isolate;min-height:100vh;width:100%;display:grid;place-items:center;overflow:hidden;padding:28px 20px;background:radial-gradient(ellipse at center,rgba(255,255,255,.48) 0%,rgba(184,238,232,0) 58%),#b8eee8;color:#302642}
          .adrian-logo-field{position:absolute;inset:0;z-index:0;overflow:hidden;pointer-events:none}
          .adrian-logo{position:absolute;left:var(--x);top:var(--y);width:var(--w);height:auto;object-fit:contain;image-rendering:auto;filter:drop-shadow(3px 6px 5px rgba(30,45,60,.22));opacity:.96;will-change:transform;animation:adrian-logo-float 5.2s ease-in-out infinite}
          .adrian-logo:nth-child(even){animation-delay:-2.1s;animation-duration:6.1s}
          .adrian-logo:nth-child(3n){animation-delay:-3.4s;animation-duration:5.7s}
          @keyframes adrian-logo-float{0%,100%{transform:translate3d(0,0,0) rotate(-3deg) scale(1)}25%{transform:translate3d(5px,-13px,0) rotate(1deg) scale(1.025)}50%{transform:translate3d(0,-24px,0) rotate(4deg) scale(1.04)}75%{transform:translate3d(-5px,-12px,0) rotate(1deg) scale(1.02)}}
          .adrian-login-card{position:relative;z-index:1;width:min(100%,460px);box-sizing:border-box;padding:34px 38px;background:#fff4d9;border:2px solid #40334d;border-radius:0;box-shadow:8px 8px 0 #40334d;text-align:center}
          .adrian-login-brand{display:flex;align-items:center;justify-content:center;gap:14px;text-align:left}
          .adrian-login-icon{width:58px;height:58px;flex:0 0 58px;display:grid;place-items:center;background:rgba(255,255,255,.5);border:2px solid #40334d;border-radius:20px}
          .adrian-login-brand h1{margin:0;font-size:25px;letter-spacing:1px;color:#302642}
          .adrian-login-brand h1 span{color:#c65b8a}
          .adrian-login-brand p{margin:5px 0 0;font-size:10px;letter-spacing:1.2px;font-weight:800;color:#302642}
          .adrian-login-intro{margin:24px 0 22px}
          .adrian-login-kicker{font-size:10px;letter-spacing:1.4px;font-weight:800;color:#356b70}
          .adrian-login-intro h2{font-size:30px;margin:10px 0 8px;color:#302642}
          .adrian-login-intro p{font-size:13px;line-height:1.6;color:#315b60;margin:0}
          .adrian-login-form{display:grid;gap:10px;text-align:left}
          .adrian-login-form label{margin-top:7px;font-size:10px;font-weight:800;letter-spacing:1px;color:#51445e}
          .adrian-login-form input{box-sizing:border-box;width:100%;min-height:48px;padding:12px 14px;background:#fffdf6;border:1.5px solid #8d7895;border-radius:14px;color:#302642;font:inherit}
          .adrian-login-form input:focus{outline:2px solid #dc78a8;outline-offset:1px}
          .adrian-login-form button,.adrian-auth-switch{width:100%;box-sizing:border-box;margin-top:12px;min-height:48px;display:flex;justify-content:center;align-items:center;gap:9px;border:2px solid #40334d;border-radius:15px;background:#f2a8c9;color:#302642;font-weight:900;cursor:pointer;font:inherit;font-weight:900}
          .adrian-login-form button:disabled{opacity:.65;cursor:wait}
          .adrian-auth-switch{margin-top:10px}
          .adrian-login-error{color:#b42342;font-size:13px;margin:0}
          .adrian-login-footer{display:flex;justify-content:space-between;gap:10px;margin-top:18px;padding-top:0;border-top:0;color:#356b70;font-size:9px;font-weight:700;letter-spacing:.5px}
          @media(max-width:1100px){.adrian-logo{opacity:.55;--w:clamp(48px,6vw,76px)!important}.adrian-logo-field{inset:0 0 0 0}}
          @media(max-width:760px){.adrian-logo{opacity:.18;--w:clamp(34px,7vw,54px)!important}.adrian-logo:nth-child(n+9){display:none}.adrian-login-card{width:min(100%,430px);padding:28px 26px}}
          @media(max-width:520px){.adrian-login-page{padding:18px 12px}.adrian-login-card{padding:24px 20px}.adrian-login-intro{margin:24px 0 18px}.adrian-logo{opacity:.12}.adrian-logo:nth-child(n+5){display:none}}
          @media(prefers-reduced-motion:reduce){.adrian-logo{animation:none}}
        `}</style>
        <section className="adrian-login-card">
          <div className="adrian-login-brand">
            <div className="adrian-login-icon"><Bot size={32} /></div>
            <div><h1>ADRIAN <span>AI</span></h1><p>DEVOPS ASSISTANT CONSOLE</p></div>
          </div>
          <div className="adrian-login-intro">
            <span className="adrian-login-kicker">YOUR DEVOPS COMMAND CENTER</span>
            <h2>Welcome back.</h2>
            <p>Sign in to access your dashboard, Adrian AI, Docker tools, and personal Ubuntu workspace.</p>
          </div>
          <form className="adrian-login-form" onSubmit={authMode === "login" ? loginToTerminal : registerAccount}>
            {authMode === "register" && <>
              <label htmlFor="register-username">USERNAME</label>
              <input id="register-username" type="text" value={registerUsername}
                onChange={(e) => setRegisterUsername(e.target.value)} placeholder="Choose a username"
                minLength={3} maxLength={100} autoComplete="username" required />
            </>}
            <label htmlFor="adrian-login-email">EMAIL ADDRESS</label>
            <input id="adrian-login-email" type="email" value={loginEmail}
              onChange={(e) => setLoginEmail(e.target.value)} placeholder="you@example.com"
              autoComplete="email" required />
            <label htmlFor="adrian-login-password">PASSWORD</label>
            <input id="adrian-login-password" type="password"
              value={authMode === "login" ? loginPassword : registerPassword}
              onChange={(e) => authMode === "login" ? setLoginPassword(e.target.value) : setRegisterPassword(e.target.value)}
              placeholder="Enter your password"
              autoComplete={authMode === "login" ? "current-password" : "new-password"}
              minLength={authMode === "register" ? 8 : undefined} required />
            {authMode === "register" && <>
              <label htmlFor="register-confirm-password">CONFIRM PASSWORD</label>
              <input id="register-confirm-password" type="password" value={registerConfirmPassword}
                onChange={(e) => setRegisterConfirmPassword(e.target.value)}
                placeholder="Confirm your password" autoComplete="new-password" minLength={8} required />
            </>}
            {loginError && <p className="adrian-login-error" role="alert">{loginError}</p>}
            <button type="submit" disabled={loading}>
              {loading ? <LoaderCircle size={17} className="spin" /> : authMode === "login" ? <ShieldCheck size={17} /> : null}
              {loading ? "PLEASE WAIT..." : authMode === "login" ? "LOGIN" : "CREATE ACCOUNT"}
            </button>
          </form>
          <button type="button" className="adrian-auth-switch"
            onClick={() => { setAuthMode(authMode === "login" ? "register" : "login"); setLoginError(""); }}>
            {authMode === "login" ? "REGISTER" : "BACK TO LOGIN"}
          </button>
          <div className="adrian-login-footer">
            <span>API: {backend}</span><span>SECURE WORKSPACE ACCESS</span>
          </div>
        </section>
      </main>
    );
  }
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-icon"><Bot size={25} /></div>
          <div>
            <h1>ADRIAN<span> AI</span></h1>
            <p>ASSISTANT CONSOLE</p>
          </div>
        </div>
        <div className="sidebar-label">WORKSPACE</div>
        <nav className="nav-menu">
          <a className="nav-item active" href="#dashboard">
            <LayoutDashboard size={18} /> Dashboard
          </a>
          <a className="nav-item" href="#assistant">
            <MessageSquare size={18} /> AI Assistant
          </a>
          <a className="nav-item" href="#containers">
            <Container size={18} /> Containers
          </a>
          <a className="nav-item" href="#activity">
            <Activity size={18} /> Activity
          </a>
        </nav>
        <div className="sidebar-label tools-label">TOOLS</div>
        <nav className="nav-menu">
          <a className="nav-item" href="#terminal">
            <Terminal size={18} /> Terminal
          </a>
          <a className="nav-item" href="#workspace">
            <FolderOpen size={18} /> Workspace
          </a>
          <a className="nav-item" href="#settings">
            <Settings size={18} /> Settings
          </a>
        </nav>
        <div className="sidebar-bottom">
          <div className="sidebar-status">
            <span className={`status-dot ${backend === "Online" ? "online" : ""}`} />
            <div>
              <strong>API CONNECTION</strong>
              <small>{backend}</small>
            </div>
          </div>
          <p className="sidebar-version">ADRIAN AI · VERSION 1.0.0</p>
        </div>
      </aside>
      <main className="main-content" id="dashboard">
        <header className="topbar">
          <div>
            <p className="eyebrow">YOUR COMMAND CENTER</p>
            <h2>Dashboard <span className="heading-star">✳</span></h2>
          </div>
          <div className="topbar-right">
            <span className="date-label">{new Date().toLocaleDateString()}</span>
            <button type="button" className="refresh-button" onClick={() => {
              terminalSocketRef.current?.close(1000, "User logged out");
              terminalSocketRef.current = null;
              setAccessToken("");
              setLoggedInUser(null);
              setLoginEmail("");
              setLoginPassword("");
              setTerminalError("");
              setTerminalOutput("Please sign in to continue.");
            }}>Log out</button>
            <div className="avatar"><Bot size={19} /></div>
          </div>
        </header>
        <section className="welcome-banner">
          <div>
            <p className="banner-kicker">SYSTEM READY_</p>
            <h3>Welcome to your DevOps workspace!</h3>
            <p>Monitor your containers, ask your AI assistant, and keep your infrastructure in check.</p>
          </div>
          <div className="banner-art"><Server size={62} strokeWidth={1.3} /></div>
        </section>
        <section className="stats-grid" aria-label="System overview">
          <article className="stat-card">
            <div className="stat-icon pink"><Server size={20} /></div>
            <div className="stat-copy">
              <span>BACKEND API</span>
              <strong>{backend}</strong>
              <small><span className={`mini-dot ${backend === "Online" ? "good" : "bad"}`} /> Service status</small>
            </div>
          </article>
          <article className="stat-card">
            <div className="stat-icon teal"><Container size={20} /></div>
            <div className="stat-copy">
              <span>DOCKER ENGINE</span>
              <strong>{dockerOnline ? "Connected" : dockerLoading ? "Checking..." : "Offline"}</strong>
              <small><span className={`mini-dot ${dockerOnline ? "good" : "bad"}`} /> Engine connection</small>
            </div>
          </article>
          <article className="stat-card">
            <div className="stat-icon purple"><Activity size={20} /></div>
            <div className="stat-copy">
              <span>RUNNING CONTAINERS</span>
              <strong>{dockerOnline ? runningCount : "—"}</strong>
              <small>Active Docker workloads</small>
            </div>
          </article>
          <article className="stat-card">
            <div className="stat-icon yellow"><ShieldCheck size={20} /></div>
            <div className="stat-copy">
              <span>AI ASSISTANT</span>
              <strong>Gemini</strong>
              <small><span className="mini-dot good" /> AI service configured</small>
            </div>
          </article>
        </section>
        <section className="panel docker-panel" id="containers">
          <div className="panel-header">
            <div className="panel-title">
              <div className="panel-icon"><Container size={19} /></div>
              <div>
                <h3>Docker Containers</h3>
                <p>Live overview from your Docker Engine</p>
              </div>
            </div>
            <button
              className="refresh-button"
              type="button"
              onClick={loadContainers}
              disabled={dockerLoading}
            >
              <RefreshCw size={15} className={dockerLoading ? "spin" : ""} />
              {dockerLoading ? "Refreshing..." : "Refresh"}
            </button>
          </div>
          {dockerError ? (
            <div className="docker-message docker-error">
              <CircleAlert size={18} />
              <div>
                <strong>Could not connect to Docker</strong>
                <p>{dockerError}</p>
              </div>
            </div>
          ) : dockerLoading && containers.length === 0 ? (
            <div className="docker-message">
              <LoaderCircle size={19} className="spin" />
              <span>Loading containers...</span>
            </div>
          ) : containers.length === 0 ? (
            <div className="docker-message empty-state">
              <Container size={22} />
              <div>
                <strong>No containers found</strong>
                <p>Start a Docker container and refresh this panel.</p>
              </div>
            </div>
          ) : (
            <div className="container-list">
              {containers.map((container) => (
                <article className="container-row" key={container.id}>
                  <div className="container-symbol"><Container size={19} /></div>
                  <div className="container-main">
                    <strong>{container.name}</strong>
                    <small>{container.image}</small>
                    <small className="container-ports">{formatPorts(container.ports)}</small>
                  </div>
                  <div className="container-meta">
                    <span className={`container-status ${container.status === "running" ? "running" : "stopped"}`}>
                      <span /> {container.status}
                    </span>
                    <small>ID: {container.id}</small>
                  </div>
                </article>
              ))}
            </div>
          )}
          <div className="panel-footer">
            <span>{containers.length} container{containers.length === 1 ? "" : "s"} detected</span>
            <span>{dockerOnline ? "Docker connection active" : "Waiting for Docker connection"}</span>
          </div>
        </section>
        <section className="panel terminal-panel" id="terminal">
          <div className="panel-header">
            <div className="panel-title">
              <div className="panel-icon terminal-icon"><Terminal size={19} /></div>
              <div>
                <h3>Ubuntu Terminal</h3>
                <p>Type Linux commands in your personal workspace</p>
              </div>
            </div>
            {loggedInUser && (
              <button
                className="refresh-button"
                type="button"
                onClick={() => {
                  setAccessToken("");
                  setLoggedInUser(null);
                  setTerminalOutput("Logged out. Sign in to use the terminal.");
                  setTerminalError("");
                }}
              >
                Log out
              </button>
            )}
          </div>
          {!accessToken ? (
            <form className="terminal-controls" onSubmit={loginToTerminal}>
              <label>
                EMAIL
                <input
                  type="email"
                  value={loginEmail}
                  onChange={(e) => setLoginEmail(e.target.value)}
                  placeholder="Your account email"
                  autoComplete="username"
                  required
                />
              </label>
              <label>
                PASSWORD
                <input
                  type="password"
                  value={loginPassword}
                  onChange={(e) => setLoginPassword(e.target.value)}
                  placeholder="Your password"
                  autoComplete="current-password"
                  required
                />
              </label>
              <button className="terminal-run-button" type="submit">Log in</button>
              {loginError && <p className="terminal-disclaimer has-error">{loginError}</p>}
            </form>
          ) : (
            <>
              <div className="terminal-controls">
                <label>
                  SIGNED IN
                  <span>{loggedInUser?.email || loggedInUser?.username || "Authenticated user"}</span>
                </label>
                <label>
                  WORKSPACE ID
                  <input
                    type="number"
                    min="1"
                    value={workspaceId}
                    onChange={(e) => setWorkspaceId(e.target.value)}
                  />
                </label>
              </div>
              <style>{`
                .adrian-xterm-host { width: 100%; min-width: 0; cursor: text; }
                .adrian-xterm-host .xterm { height: 100%; width: 100%; }
                .adrian-xterm-host .xterm-viewport { overflow-y: auto !important; }
                .adrian-xterm-host .xterm-helper-textarea {
                  opacity: 0 !important;
                  position: absolute !important;
                }
                .terminal-window .terminal-output {
                  text-align: left !important;
                  justify-content: flex-start !important;
                  align-items: flex-start !important;
                  display: block !important;
                  width: 100% !important;
                  margin-left: 0 !important;
                  margin-right: 0 !important;
                }
                .terminal-window form { text-align: left !important; }
                .terminal-window form input { text-align: left !important; }
              `}</style>
              <div className="terminal-window" style={{ background: "#171923", border: "1px solid #454052", overflow: "hidden" }}>
                <div className="terminal-window-bar">
                  <span><i /> <i /> <i /></span>
                  <strong>ADRIAN AI / CLI</strong>
                  <span className="terminal-readonly">{terminalConnection}</span>
                </div>
                <div
                  ref={xtermHostRef}
                  className="adrian-xterm-host"
                  onClick={() => xtermRef.current?.focus()}
                  onMouseDown={() => xtermRef.current?.focus()}
                  style={{
                    height: 340,
                    padding: "12px 14px",
                    background: "#171923",
                    boxSizing: "border-box",
                    textAlign: "left",
                  }}
                />
              </div>
            </>
          )}
        </section>
        <div className="content-grid">
          <section className="panel chat-panel" id="assistant">
            <div className="panel-header">
              <div className="panel-title">
                <div className="panel-icon chat-icon"><Bot size={19} /></div>
                <div>
                  <h3>AI Assistant</h3>
                  <p>Powered by Google Gemini</p>
                </div>
              </div>
              <span className="live-pill"><span /> LIVE</span>
            </div>
            <div className="chat-messages">
              {messages.map((item, index) => (
                <div className={`chat-message ${item.role}`} key={`${item.role}-${index}`}>
                  <div className="message-avatar">
                    {item.role === "assistant" ? <Bot size={16} /> : <span>YOU</span>}
                  </div>
                  <div className="message-bubble">
                    <small>{item.role === "assistant" ? "ADRIAN AI" : "YOU"}</small>
                    <p>{item.content}</p>
                  </div>
                </div>
              ))}
              {loading && (
                <div className="chat-message assistant">
                  <div className="message-avatar"><Bot size={16} /></div>
                  <div className="message-bubble">
                    <small>ADRIAN AI</small>
                    <p className="thinking"><LoaderCircle size={15} className="spin" /> Thinking...</p>
                  </div>
                </div>
              )}
            </div>
            <form className="chat-form" onSubmit={sendMessage}>
              <input
                type="text"
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder="Ask me about Docker, Linux, AWS, Kubernetes..."
                aria-label="Message the Adrian AI Assistant"
                maxLength={4000}
              />
              <button type="submit" disabled={loading || !message.trim()} aria-label="Send message">
                {loading ? <LoaderCircle size={18} className="spin" /> : <Send size={18} />}
              </button>
            </form>
            <p className="chat-hint">ENTER TO SEND · AI-GENERATED ANSWERS MAY NEED VERIFICATION</p>
          </section>
          <section className="panel health-panel" id="activity">
            <div className="panel-header">
              <div className="panel-title">
                <div className="panel-icon health-icon"><Activity size={19} /></div>
                <div>
                  <h3>System Health</h3>
                  <p>Service connection overview</p>
                </div>
              </div>
            </div>
            <div className="health-list">
              <div className="health-item">
                <div className="health-item-icon"><Server size={17} /></div>
                <div><strong>FastAPI Backend</strong><small>/api</small></div>
                <span className={`health-state ${backend === "Online" ? "ok" : "fail"}`}>
                  {backend === "Online" ? <CircleCheck size={16} /> : <CircleAlert size={16} />}
                  {backend}
                </span>
              </div>
              <div className="health-item">
                <div className="health-item-icon"><Container size={17} /></div>
                <div><strong>Docker Engine</strong><small>Container runtime</small></div>
                <span className={`health-state ${dockerOnline ? "ok" : "fail"}`}>
                  {dockerOnline ? <CircleCheck size={16} /> : <CircleAlert size={16} />}
                  {dockerOnline ? "Online" : "Offline"}
                </span>
              </div>
              <div className="health-item">
                <div className="health-item-icon"><Cpu size={17} /></div>
                <div><strong>Gemini AI</strong><small>AI response service</small></div>
                <span className="health-state ok"><CircleCheck size={16} /> Ready</span>
              </div>
              <div className="health-item">
                <div className="health-item-icon"><HardDrive size={17} /></div>
                <div><strong>Workspace</strong><small>Local project files</small></div>
                <span className="health-state ok"><CircleCheck size={16} /> Ready</span>
              </div>
            </div>
            <div className="health-note">
              <ShieldCheck size={17} />
              <span>Monitoring is read-only. No container actions are performed from this dashboard.</span>
            </div>
            <a className="docs-link" href="/docs" target="_blank" rel="noreferrer">
              Open API documentation <ChevronRight size={15} />
            </a>
          </section>
        </div>
        <footer className="page-footer">
          <span>✳ BUILT FOR YOUR DEVOPS WORKFLOW</span>
          <span>ADRIAN AI ASSISTANT · 2026</span>
        </footer>
      </main>
    </div>
  );
}
export default App;
