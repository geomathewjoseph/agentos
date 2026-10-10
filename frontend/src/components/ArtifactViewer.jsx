import { useState } from 'react';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { atomDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { File, ChevronRight, ChevronDown, Folder, Copy, Check } from 'lucide-react';

export default function ArtifactViewer({ artifacts }) {
  const [selectedFile, setSelectedFile] = useState(null);
  const [copied, setCopied] = useState(false);

  const activeFile = selectedFile || (Object.keys(artifacts).length > 0 ? Object.keys(artifacts)[0] : null);

  // Group paths into a tree structure
  const buildTree = (paths) => {
    const tree = {};
    paths.forEach(path => {
      const parts = path.split('/');
      let current = tree;
      for (let i = 0; i < parts.length; i++) {
        const part = parts[i];
        if (i === parts.length - 1) {
          current[part] = null; // file
        } else {
          current[part] = current[part] || {};
          current = current[part];
        }
      }
    });
    return tree;
  };

  const fileTree = buildTree(Object.keys(artifacts).sort());

  const handleCopy = () => {
    if (activeFile) {
      navigator.clipboard.writeText(artifacts[activeFile]);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const TreeNode = ({ name, node, path = '' }) => {
    const [isOpen, setIsOpen] = useState(true);
    const fullPath = path ? `${path}/${name}` : name;
    const isFile = node === null;

    if (isFile) {
      return (
        <div 
          style={{ 
            display: 'flex', alignItems: 'center', gap: '8px', padding: '7px 12px', 
            cursor: 'pointer', borderRadius: '10px',
            backgroundColor: activeFile === fullPath ? 'rgba(255, 255, 255, 0.08)' : 'transparent',
            color: activeFile === fullPath ? 'var(--text-primary)' : 'var(--text-secondary)',
            transition: 'all 0.15s ease'
          }}
          onClick={() => setSelectedFile(fullPath)}
        >
          <File size={14} />
          <span style={{ fontSize: '0.88rem' }}>{name}</span>
        </div>
      );
    }

    return (
      <div>
        <div 
          style={{ 
            display: 'flex', alignItems: 'center', gap: '6px', padding: '6px 8px', 
            cursor: 'pointer', color: 'var(--text-primary)', borderRadius: '10px',
            transition: 'all 0.15s ease'
          }}
          onClick={() => setIsOpen(!isOpen)}
        >
          {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          <Folder size={14} style={{ color: 'var(--accent-color)' }} />
          <span style={{ fontSize: '0.88rem', fontWeight: 500 }}>{name}</span>
        </div>
        {isOpen && (
          <div style={{ paddingLeft: '16px', borderLeft: '1px solid var(--border-color)', marginLeft: '12px' }}>
            {Object.keys(node).map(childName => (
              <TreeNode key={childName} name={childName} node={node[childName]} path={fullPath} />
            ))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {Object.keys(artifacts).length === 0 ? (
        <div style={{ padding: '32px', textAlign: 'center', color: 'var(--text-muted)' }}>
          <p>No files generated yet.</p>
        </div>
      ) : (
        <>
          <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border-color)', maxHeight: '32%', overflowY: 'auto' }}>
            {Object.keys(fileTree).map(name => (
              <TreeNode key={name} name={name} node={fileTree[name]} />
            ))}
          </div>
          
          {activeFile && (
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', padding: '12px' }}>
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', borderRadius: '16px', border: '1px solid rgba(255, 255, 255, 0.08)', backgroundColor: '#18191a' }}>
                <div style={{ padding: '10px 16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', backgroundColor: 'rgba(255, 255, 255, 0.03)', borderBottom: '1px solid var(--border-color)' }}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>{activeFile}</span>
                  <button className="icon-btn" onClick={handleCopy} title="Copy code">
                    {copied ? <Check size={16} style={{color: 'var(--success)'}}/> : <Copy size={16} />}
                  </button>
                </div>
                <div style={{ flex: 1, overflow: 'auto', backgroundColor: '#141414' }}>
                  <SyntaxHighlighter 
                    language={activeFile.split('.').pop()} 
                    style={atomDark}
                    customStyle={{ margin: 0, padding: '16px', background: 'transparent', fontSize: '0.85rem' }}
                    showLineNumbers={true}
                  >
                    {artifacts[activeFile] || ''}
                  </SyntaxHighlighter>
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
