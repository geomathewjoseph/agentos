import { useState, useEffect } from 'react';
import { X, Save, Key, Cpu } from 'lucide-react';
import { motion } from 'framer-motion';

export default function SettingsModal({ onClose }) {
  const [activeTab, setActiveTab] = useState('api');
  const [apiKeys, setApiKeys] = useState({});
  const [models, setModels] = useState({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    // Fetch current config
    Promise.all([
      fetch('/api/config').then(r => r.json()),
      fetch('/api/models').then(r => r.json())
    ]).then(([configData, modelsData]) => {
      setApiKeys(configData.keys || {});
      setModels(modelsData.models || {});
      setLoading(false);
    }).catch(err => {
      console.error("Failed to load settings", err);
      setLoading(false);
    });
  }, []);

  const handleKeyChange = (key, value) => {
    setApiKeys(prev => ({ ...prev, [key]: value }));
  };

  const handleModelChange = (task, provider) => {
    // We only track the top selection for simplicity in UI
    setModels(prev => {
      const newModels = {...prev};
      const chain = [...newModels[task].chain];
      const idx = chain.findIndex(c => c.provider === provider);
      if (idx > 0) {
        const item = chain.splice(idx, 1)[0];
        chain.unshift(item);
        newModels[task].chain = chain;
      }
      return newModels;
    });
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ keys: apiKeys })
      });
      const selections = {};
      Object.keys(models).forEach(task => {
        if (models[task].chain.length > 0) {
          selections[task] = models[task].chain[0].provider;
        }
      });
      await fetch('/api/models', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ selections })
      });
      setTimeout(() => {
        setSaving(false);
        onClose();
      }, 500);
    } catch (err) {
      console.error('Save failed', err);
      setSaving(false);
    }
  };

  return (
    <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.65)', backdropFilter: 'blur(8px)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 50 }}>
      <motion.div 
        initial={{ opacity: 0, scale: 0.94, y: 15 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        transition={{ type: 'spring', damping: 25, stiffness: 220 }}
        style={{ width: '100%', maxWidth: '620px', backgroundColor: 'rgba(24, 24, 24, 0.96)', backdropFilter: 'blur(24px)', borderRadius: '26px', border: '1px solid rgba(255, 255, 255, 0.12)', overflow: 'hidden', boxShadow: '0 30px 60px -12px rgba(0, 0, 0, 0.65)' }}
      >
        <div style={{ padding: '22px 28px', borderBottom: '1px solid var(--border-color)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h2 style={{ margin: 0, fontSize: '1.25rem', fontWeight: 600 }}>Settings</h2>
          <button className="icon-btn" onClick={onClose}><X size={20} /></button>
        </div>

        {/* Segmented Pill Tabs */}
        <div style={{ padding: '12px 28px' }}>
          <div style={{ display: 'flex', background: 'rgba(255, 255, 255, 0.04)', padding: '4px', borderRadius: '9999px', border: '1px solid rgba(255, 255, 255, 0.06)' }}>
            <button 
              style={{ flex: 1, padding: '8px 16px', background: activeTab === 'api' ? 'rgba(255, 255, 255, 0.12)' : 'transparent', borderRadius: '9999px', border: 'none', color: activeTab === 'api' ? 'var(--text-primary)' : 'var(--text-muted)', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', fontWeight: 500, fontSize: '0.9rem', transition: 'all 0.2s ease', fontFamily: 'var(--font-sans)' }}
              onClick={() => setActiveTab('api')}
            >
              <Key size={15} /> API Keys
            </button>
            <button 
              style={{ flex: 1, padding: '8px 16px', background: activeTab === 'models' ? 'rgba(255, 255, 255, 0.12)' : 'transparent', borderRadius: '9999px', border: 'none', color: activeTab === 'models' ? 'var(--text-primary)' : 'var(--text-muted)', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', fontWeight: 500, fontSize: '0.9rem', transition: 'all 0.2s ease', fontFamily: 'var(--font-sans)' }}
              onClick={() => setActiveTab('models')}
            >
              <Cpu size={15} /> Models
            </button>
          </div>
        </div>

        <div style={{ padding: '16px 28px 24px', maxHeight: '420px', overflowY: 'auto' }}>
          {loading ? (
            <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-muted)' }}>Loading...</div>
          ) : (
            <>
              {activeTab === 'api' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                  <p style={{ margin: 0, fontSize: '0.88rem', color: 'var(--text-muted)' }}>Provide API keys for your preferred models. Only the active ones are required.</p>
                  {Object.keys(apiKeys).map(key => (
                    <div key={key} style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                      <label style={{ fontSize: '0.85rem', fontWeight: 500, color: 'var(--text-secondary)' }}>{key}</label>
                      <input 
                        type="password" 
                        value={apiKeys[key]} 
                        onChange={(e) => handleKeyChange(key, e.target.value)}
                        placeholder="sk-..." 
                        style={{ width: '100%', borderRadius: '14px', backgroundColor: 'rgba(255, 255, 255, 0.04)', border: '1px solid rgba(255, 255, 255, 0.1)' }}
                      />
                    </div>
                  ))}
                </div>
              )}

              {activeTab === 'models' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                  <p style={{ margin: 0, fontSize: '0.88rem', color: 'var(--text-muted)' }}>Select the primary provider for each agent role. The system will automatically fall back to others if rate-limited.</p>
                  {Object.keys(models).map(task => (
                    <div key={task} style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                      <label style={{ fontSize: '0.88rem', fontWeight: 600, textTransform: 'capitalize' }}>{task} Agent</label>
                      <select 
                        style={{ width: '100%', padding: '10px 14px', borderRadius: '14px', backgroundColor: 'rgba(255, 255, 255, 0.04)', border: '1px solid rgba(255, 255, 255, 0.1)', color: 'var(--text-primary)', outline: 'none', fontFamily: 'var(--font-sans)', cursor: 'pointer' }}
                        value={models[task].chain[0]?.provider || ''}
                        onChange={(e) => handleModelChange(task, e.target.value)}
                      >
                        {models[task].chain.map(c => (
                          <option key={c.provider} value={c.provider} style={{ backgroundColor: '#212121' }}>
                            {c.provider} ({c.model})
                          </option>
                        ))}
                      </select>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>

        <div style={{ padding: '16px 28px', borderTop: '1px solid var(--border-color)', display: 'flex', justifyContent: 'flex-end', gap: '12px', backgroundColor: 'rgba(255, 255, 255, 0.02)' }}>
          <button className="btn btn-secondary" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" onClick={handleSave} disabled={loading || saving}>
            {saving ? 'Saving...' : <><Save size={16} /> Save Changes</>}
          </button>
        </div>
      </motion.div>
    </div>
  );
}
