import { useState, useRef, useEffect } from 'react';
import { Menu, Plus, Settings, User, Cpu, ArrowUp, Code, LayoutTemplate, Database, TestTube, FolderTree, X, Mic, MicOff, Download } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import clsx from 'clsx';
import './App.css';
import PipelineViewer from './components/PipelineViewer';
import ArtifactViewer from './components/ArtifactViewer';
import SettingsModal from './components/SettingsModal';
import Logo from './components/Logo';

function App() {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [artifactsOpen, setArtifactsOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [goal, setGoal] = useState('');
  const [chatState, setChatState] = useState('initial'); // 'initial', 'running', 'done', 'error'
  const [errorMsg, setErrorMsg] = useState('');
  const [messages, setMessages] = useState([]);
  const [artifacts, setArtifacts] = useState({});
  const [ws, setWs] = useState(null);

  // Restore latest generated artifacts on page load
  useEffect(() => {
    fetch('/api/artifacts')
      .then(res => res.json())
      .then(data => {
        if (data && data.artifacts && Object.keys(data.artifacts).length > 0) {
          setArtifacts(data.artifacts);
        }
      })
      .catch(() => {});
  }, []);

  
  // Voice Recording & Whisper AI State
  const [isListening, setIsListening] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  
  const textareaRef = useRef(null);
  const messagesEndRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const streamRef = useRef(null);
  const timerIntervalRef = useRef(null);
  const recognitionRef = useRef(null);
  const baseGoalRef = useRef('');

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, chatState]);

  // Enforce latest AgentOS favicon in active browser tabs and bust browser cache
  useEffect(() => {
    try {
      const head = document.head || document.getElementsByTagName('head')[0];
      const timestamp = Date.now();
      
      // Remove stale links
      const staleLinks = document.querySelectorAll("link[rel*='icon'], link[rel='shortcut icon']");
      staleLinks.forEach(el => el.remove());

      const iconSvg = document.createElement('link');
      iconSvg.rel = 'icon';
      iconSvg.type = 'image/svg+xml';
      iconSvg.href = `/favicon.svg?v=${timestamp}`;
      head.appendChild(iconSvg);

      const iconPng = document.createElement('link');
      iconPng.rel = 'icon';
      iconPng.type = 'image/png';
      iconPng.sizes = '32x32';
      iconPng.href = `/favicon.png?v=${timestamp}`;
      head.appendChild(iconPng);

      const iconIco = document.createElement('link');
      iconIco.rel = 'shortcut icon';
      iconIco.href = `/favicon.ico?v=${timestamp}`;
      head.appendChild(iconIco);
    } catch (e) {
      console.warn('Favicon update error:', e);
    }
  }, []);

  // Clean up media recorder, stream, and recognition on unmount
  useEffect(() => {
    return () => {
      if (timerIntervalRef.current) clearInterval(timerIntervalRef.current);
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(t => t.stop());
      }
      if (recognitionRef.current) {
        try { recognitionRef.current.abort(); } catch (e) {}
      }
    };
  }, []);

  const handleInput = (e) => {
    setGoal(e.target.value);
    e.target.style.height = 'auto';
    e.target.style.height = `${Math.min(e.target.scrollHeight, 200)}px`;
  };

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      audioChunksRef.current = [];

      let mimeType = 'audio/webm;codecs=opus';
      if (!window.MediaRecorder || !MediaRecorder.isTypeSupported(mimeType)) {
        mimeType = MediaRecorder?.isTypeSupported?.('audio/webm') ? 'audio/webm' : '';
      }
      const mediaRecorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;

      mediaRecorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) {
          audioChunksRef.current.push(e.data);
        }
      };

      mediaRecorder.start(250);
      setIsListening(true);
      setRecordingSeconds(0);
      baseGoalRef.current = goal;

      timerIntervalRef.current = setInterval(() => {
        setRecordingSeconds(prev => prev + 1);
      }, 1000);

      // Start Web Speech API as simultaneous live interim preview
      const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (SpeechRecognition) {
        try {
          const rec = new SpeechRecognition();
          rec.continuous = true;
          rec.interimResults = true;
          rec.lang = navigator.language || 'en-US';

          rec.onresult = (event) => {
            let finalStr = '';
            let interimStr = '';
            for (let i = 0; i < event.results.length; i++) {
              if (event.results[i].isFinal) {
                finalStr += event.results[i][0].transcript + ' ';
              } else {
                interimStr += event.results[i][0].transcript;
              }
            }
            const liveText = (finalStr + interimStr).trim();
            const base = baseGoalRef.current.trim();
            const combined = base ? `${base} ${liveText}` : liveText;
            setGoal(combined);
            if (textareaRef.current) {
              textareaRef.current.style.height = 'auto';
              textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`;
            }
          };

          rec.onerror = (e) => {
            console.warn('Live preview speech error:', e.error);
          };

          rec.onend = () => {
            // Do not stop recording on silence; user controls recording manually
          };

          recognitionRef.current = rec;
          rec.start();
        } catch (e) {
          console.warn('Live SpeechRecognition preview start failed:', e);
        }
      }
    } catch (err) {
      console.error('Microphone error:', err);
      if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
        alert('Microphone access was denied. Please allow microphone permissions in your browser address bar.');
      } else {
        alert('Could not start microphone: ' + (err.message || err));
      }
      setIsListening(false);
    }
  };

  const stopRecording = () => {
    setIsListening(false);
    if (timerIntervalRef.current) {
      clearInterval(timerIntervalRef.current);
      timerIntervalRef.current = null;
    }

    if (recognitionRef.current) {
      try { recognitionRef.current.stop(); } catch (e) {}
    }

    const recorder = mediaRecorderRef.current;
    if (!recorder || recorder.state === 'inactive') {
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(t => t.stop());
        streamRef.current = null;
      }
      return;
    }

    setIsTranscribing(true);

    recorder.onstop = async () => {
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(t => t.stop());
        streamRef.current = null;
      }

      const mimeType = recorder.mimeType || 'audio/webm';
      const audioBlob = new Blob(audioChunksRef.current, { type: mimeType });

      if (audioBlob.size > 800) {
        const formData = new FormData();
        const ext = mimeType.includes('wav') ? 'wav' : (mimeType.includes('ogg') ? 'ogg' : 'webm');
        formData.append('file', audioBlob, `recording.${ext}`);

        try {
          const resp = await fetch('/api/transcribe', {
            method: 'POST',
            body: formData,
          });

          if (resp.ok) {
            const data = await resp.json();
            if (data.status === 'success' && data.text) {
              const base = baseGoalRef.current.trim();
              const whisperText = data.text.trim();
              const combined = base ? `${base} ${whisperText}` : whisperText;
              setGoal(combined);
              if (textareaRef.current) {
                textareaRef.current.style.height = 'auto';
                textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`;
              }
            }
          }
        } catch (err) {
          console.warn('Whisper API transcription failed, keeping preview text:', err);
        }
      }
      setIsTranscribing(false);
    };

    recorder.stop();
  };

  const toggleListening = () => {
    if (isListening) {
      stopRecording();
    } else {
      startRecording();
    }
  };

  const startPipeline = (forcedGoal = null) => {
    const finalGoal = forcedGoal || goal;
    if (!finalGoal.trim()) return;

    if (isListening) {
      stopRecording();
    }

    setGoal('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }

    setChatState('running');
    setErrorMsg('');
    setMessages([{ role: 'user', content: finalGoal }]);
    setArtifacts({});

    if (window.innerWidth < 1024) setSidebarOpen(false);
    
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const socket = new WebSocket(`${protocol}//${window.location.host}/api/run`);
    
    socket.onopen = () => {
      socket.send(JSON.stringify({ goal: finalGoal }));
    };

    socket.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === 'update' && data.state?.code) {
        setArtifacts(prev => ({...prev, ...data.state.code}));
      }
      if (data.type === 'done') {
        setChatState('done');
      }
      if (data.type === 'error') {
        setErrorMsg(data.message || 'Pipeline failed');
        setChatState('error');
      }
    };

    socket.onerror = (err) => {
      console.error('WebSocket connection error:', err);
      setErrorMsg('Connection error to AgentOS server');
      setChatState('error');
    };

    socket.onclose = (event) => {
      setChatState(prev => {
        if (prev === 'running') {
          if (!event.wasClean) {
            setErrorMsg('Connection to server lost unexpectedly');
            return 'error';
          }
          return 'done';
        }
        return prev;
      });
    };

    setWs(socket);
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      startPipeline();
    }
  };

  return (
    <div className="app-layout">
      {/* Sidebar */}
      <motion.aside 
        className={clsx('sidebar', !sidebarOpen && 'collapsed')}
        initial={false}
        animate={{ width: sidebarOpen ? 260 : 0 }}
      >
        <div className="sidebar-header">
          <div className="sidebar-brand">
            <Logo size={24} />
            <span>AgentOS</span>
          </div>
        </div>
        
        <div className="sidebar-content">
          {sidebarOpen && (
            <button 
              className="btn btn-secondary" 
              style={{ width: '100%', justifyContent: 'flex-start', borderRadius: '9999px', padding: '10px 18px', border: '1px solid rgba(255, 255, 255, 0.08)' }} 
              onClick={() => window.location.reload()}
            >
              <Plus size={16} /> New Chat
            </button>
          )}
        </div>

        <div className="sidebar-footer">
          {sidebarOpen && (
            <button 
              className="icon-btn" 
              style={{ width: '100%', justifyContent: 'flex-start', gap: '10px', padding: '10px 16px', borderRadius: '14px' }} 
              onClick={() => setSettingsOpen(true)}
            >
              <Settings size={18} /> Settings
            </button>
          )}
        </div>
      </motion.aside>

      {/* Main Area */}
      <main className="main-area">
        <header className="chat-header">
          <div className="menu-toggle" style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <button className="icon-btn" onClick={() => setSidebarOpen(!sidebarOpen)}>
              <Menu size={20} />
            </button>
            {!sidebarOpen && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 600, fontSize: '0.95rem', color: 'var(--text-primary)' }}>
                <Logo size={22} />
                <span>AgentOS</span>
              </div>
            )}
          </div>
        </header>

        {chatState === 'initial' ? (
          <div className="greeting">
            <motion.div 
              initial={{ scale: 0.85, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ duration: 0.35, ease: 'easeOut' }}
              style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '20px' }}
            >
              <Logo size={56} />
              <h1>How can I help you today?</h1>
            </motion.div>
            <div className="chips">
              <button className="chip" onClick={() => startPipeline('Build a CLI Tool')}>
                <div className="chip-title"><Code size={16}/> CLI Tool</div>
                <div className="chip-desc">A Python command-line app</div>
              </button>
              <button className="chip" onClick={() => startPipeline('Build a Web App')}>
                <div className="chip-title"><LayoutTemplate size={16}/> Web App</div>
                <div className="chip-desc">Vite + React frontend</div>
              </button>
              <button className="chip" onClick={() => startPipeline('Build a REST API')}>
                <div className="chip-title"><Database size={16}/> REST API</div>
                <div className="chip-desc">FastAPI backend server</div>
              </button>
              <button className="chip" onClick={() => startPipeline('Write Unit Tests')}>
                <div className="chip-title"><TestTube size={16}/> Unit Tests</div>
                <div className="chip-desc">Pytest suite coverage</div>
              </button>
            </div>
          </div>
        ) : (
          <div className="chat-stream">
            {messages.map((msg, i) => (
              <div key={i} className={`chat-bubble ${msg.role}-bubble`}>
                <div className="bubble-avatar">
                  {msg.role === 'user' ? <User size={16} /> : <Logo size={18} />}
                </div>
                <div className="bubble-content">
                  {msg.content}
                </div>
              </div>
            ))}
            
            <div className="chat-bubble agent-bubble">
              <div className="bubble-avatar"><Logo size={18} /></div>
              <div className="bubble-content" style={{width: '100%'}}>
                 <PipelineViewer ws={ws} status={chatState} />
                 {chatState === 'error' && errorMsg && (
                   <div style={{ color: 'var(--error)', marginTop: '12px', padding: '12px', backgroundColor: 'rgba(239, 68, 68, 0.1)', borderRadius: '8px', border: '1px solid rgba(239, 68, 68, 0.2)' }}>
                     {errorMsg}
                   </div>
                 )}
              </div>
            </div>
            <div ref={messagesEndRef} />
          </div>
        )}

        <div className="input-area">
          <AnimatePresence>
            {isListening && (
              <motion.div 
                className="voice-status-bar"
                initial={{ opacity: 0, y: 10, scale: 0.95 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: 5, scale: 0.95 }}
              >
                <div className="voice-recording-indicator">
                  <span className="recording-dot" />
                  <span className="recording-timer">
                    {Math.floor(recordingSeconds / 60)}:{String(recordingSeconds % 60).padStart(2, '0')}
                  </span>
                  <span className="recording-label">Listening... Speak naturally</span>
                </div>
                <div className="sound-wave">
                  <span className="bar bar-1" />
                  <span className="bar bar-2" />
                  <span className="bar bar-3" />
                  <span className="bar bar-4" />
                  <span className="bar bar-5" />
                </div>
                <button 
                  type="button" 
                  className="voice-done-btn"
                  onClick={stopRecording}
                  title="Finish recording"
                >
                  Done
                </button>
              </motion.div>
            )}
            {isTranscribing && (
              <motion.div 
                className="voice-transcribing-bar"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
              >
                <span className="transcribing-spinner" />
                <span>Refining with Whisper AI...</span>
              </motion.div>
            )}
          </AnimatePresence>

          <div className="input-box">
            <textarea
              ref={textareaRef}
              value={goal}
              onChange={handleInput}
              onKeyDown={handleKeyDown}
              placeholder={isListening ? "Listening... Speak your prompt now" : (isTranscribing ? "Transcribing speech..." : "Message AgentOS...")}
              disabled={chatState === 'running' || isTranscribing}
              rows={1}
            />
            <div className="input-actions">
              <button 
                type="button"
                className={clsx('mic-btn', isListening && 'listening')}
                onClick={toggleListening}
                disabled={chatState === 'running' || isTranscribing}
                title={isListening ? "Stop voice input" : "Voice to text (Speak)"}
              >
                {isListening ? <MicOff size={18} /> : <Mic size={18} />}
              </button>
              <button 
                type="button"
                className="send-btn"
                onClick={() => startPipeline()}
                disabled={!goal.trim() || chatState === 'running' || isTranscribing}
                title="Send message"
              >
                <ArrowUp size={18} strokeWidth={2.5} />
              </button>
            </div>
          </div>
        </div>

        {/* Floating Artifacts Button */}
        {Object.keys(artifacts).length > 0 && !artifactsOpen && (
          <motion.button 
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            className="btn btn-secondary"
            style={{ position: 'absolute', top: 18, right: 20, zIndex: 15, backgroundColor: 'rgba(28, 28, 28, 0.85)', backdropFilter: 'blur(16px)', border: '1px solid rgba(255, 255, 255, 0.12)', borderRadius: '9999px', padding: '8px 18px', boxShadow: '0 4px 16px rgba(0, 0, 0, 0.25)' }}
            onClick={() => setArtifactsOpen(true)}
          >
            <FolderTree size={16} /> Code
          </motion.button>
        )}
      </main>

      {/* Artifacts Drawer */}
      <AnimatePresence>
        {artifactsOpen && (
          <motion.aside 
            className="artifacts-drawer"
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', damping: 25, stiffness: 200 }}
          >
            <div className="drawer-header" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <h2 style={{fontSize: '1rem', margin: 0, fontWeight: 500}}>Artifacts</h2>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <a 
                  href="/api/artifacts/download" 
                  className="btn btn-secondary" 
                  style={{ fontSize: '0.8rem', padding: '5px 12px', display: 'flex', alignItems: 'center', gap: '6px', textDecoration: 'none', borderRadius: '8px' }}
                  download="agentos_project.zip"
                  title="Download complete project as ZIP"
                >
                  <Download size={14} /> Export ZIP
                </a>
                <button className="icon-btn" onClick={() => setArtifactsOpen(false)}>
                  <X size={18} />
                </button>
              </div>
            </div>

            <div className="drawer-content">
              <ArtifactViewer artifacts={artifacts} />
            </div>
          </motion.aside>
        )}
      </AnimatePresence>

      {/* Settings Modal */}
      {settingsOpen && <SettingsModal onClose={() => setSettingsOpen(false)} />}
    </div>
  );
}

export default App;
