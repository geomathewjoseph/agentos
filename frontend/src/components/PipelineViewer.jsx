import { useState, useEffect, useRef } from 'react';
import { motion } from 'framer-motion';
import { Loader2, CheckCircle2, AlertCircle, Play } from 'lucide-react';

export default function PipelineViewer({ ws, status }) {
  const [nodes, setNodes] = useState([]);
  const [logs, setLogs] = useState([]);
  const logsEndRef = useRef(null);

  useEffect(() => {
    if (!ws) return;

    const handleMessage = (event) => {
      let data;
      try {
        data = JSON.parse(event.data);
      } catch(e) {
        console.warn('Non-JSON WebSocket message:', event.data);
        return;
      }
      
      if (data.node === 'system') return; // system is not a pipeline node

      if (data.type === 'update') {
        setNodes(prev => {
          const existing = [...prev];
          const idx = existing.findIndex(n => n.name === data.node);
          if (idx >= 0) {
            existing[idx] = { ...existing[idx], state: data.state, status: 'completed' };
          } else {
            existing.push({ name: data.node, state: data.state, status: 'completed' });
          }
          return existing;
        });
      }
      
      if (data.type === 'status') {
        setNodes(prev => {
          const existing = [...prev];
          const idx = existing.findIndex(n => n.name === data.node);
          if (idx >= 0) {
            existing[idx] = { ...existing[idx], status: 'running' };
          } else {
            existing.push({ name: data.node, status: 'running' });
          }
          return existing;
        });
      }

      if (data.type === 'log') {
        setLogs(prev => [...prev, data.log]);
        setTimeout(() => {
          logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
        }, 50);
      }
    };

    ws.addEventListener('message', handleMessage);
    return () => ws.removeEventListener('message', handleMessage);
  }, [ws]);

  const getNodeIcon = (nodeStatus) => {
    switch(nodeStatus) {
      case 'running': return <Loader2 size={14} className="animate-spin" style={{color: 'var(--text-primary)'}}/>;
      case 'completed': return <CheckCircle2 size={14} style={{color: 'var(--success)'}}/>;
      case 'error': return <AlertCircle size={14} style={{color: 'var(--error)'}}/>;
      default: return <Play size={14} style={{color: 'var(--text-muted)'}}/>;
    }
  };

  return (
    <div className="pipeline-viewer">
      
      {/* Header */}
      <div className="pipeline-header">
        <h3 style={{ margin: 0, fontSize: '0.9rem', fontWeight: 500 }}>AgentOS Pipeline</h3>
        <span style={{ 
          fontSize: '0.75rem', 
          fontWeight: 500,
          color: status === 'running' ? 'var(--text-primary)' : (status === 'error' ? 'var(--error)' : 'var(--success)')
        }}>
          {status.charAt(0).toUpperCase() + status.slice(1)}
        </span>
      </div>

      {/* Nodes List */}
      <div className="pipeline-nodes">
        {nodes.length === 0 && <span style={{color: 'var(--text-muted)', fontSize: '0.85rem'}}>Initializing pipeline...</span>}
        
        {nodes.map((node, i) => (
          <motion.div 
            key={i}
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className={`node-item ${node.status === 'running' ? 'running' : ''}`}
          >
            {getNodeIcon(node.status)}
            <span>{node.name.replace(/_/g, ' ')}</span>
          </motion.div>
        ))}
      </div>

      {/* Terminal Logs */}
      <div className="pipeline-logs">
        <details open>
          <summary>System Logs</summary>
          <div className="logs-container">
            {logs.map((log, i) => (
              <div key={i} style={{ marginBottom: '4px', display: 'flex', gap: '8px', lineHeight: 1.4 }}>
                <span style={{ color: '#525252', minWidth: '70px' }}>[{log.timestamp}]</span>
                <span style={{ color: log.level === 'error' ? '#ef4444' : log.level === 'warning' ? '#f59e0b' : log.level === 'success' ? '#10b981' : '#a3a3a3', minWidth: '90px' }}>
                  [{log.source}]
                </span>
                <span style={{ color: log.level === 'error' ? '#fca5a5' : log.level === 'warning' ? '#fcd34d' : '#e5e5e5', wordBreak: 'break-all' }}>
                  {log.message}
                </span>
              </div>
            ))}
            <div ref={logsEndRef} />
          </div>
        </details>
      </div>
    </div>
  );
}
