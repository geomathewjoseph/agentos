// app.js - Minimal AgentOS Frontend Logic

lucide.createIcons();

// Elements
const el = {
    mainContent: document.getElementById('main-content'),
    goalInput: document.getElementById('goal-input'),
    btnStart: document.getElementById('btn-start-build'),
    chatStream: document.getElementById('chat-stream'),
    userPromptDisplay: document.getElementById('user-prompt-display'),
    
    pipelineNodes: document.getElementById('pipeline-nodes'),
    pipelineBadge: document.getElementById('pipeline-status-badge'),
    terminalOutput: document.getElementById('terminal-output'),
    
    drawer: document.getElementById('artifacts-drawer'),
    btnCloseDrawer: document.getElementById('btn-close-drawer'),
    btnOpenArtifacts: document.getElementById('btn-open-artifacts'),
    fileTree: document.getElementById('file-tree'),
    codeViewer: document.getElementById('code-viewer'),
    codeContent: document.getElementById('code-content'),
    codeFilename: document.getElementById('code-viewer-filename'),
    btnBackTree: document.getElementById('btn-back-tree'),
    btnCopyCode: document.getElementById('btn-copy-code'),
    
    btnSettings: document.getElementById('btn-settings'),
    modalSettings: document.getElementById('modal-settings'),
    modalCloses: document.querySelectorAll('.modal-close'),
    formApiKeys: document.getElementById('form-api-keys'),
    formModels: document.getElementById('form-models'),
    btnSaveSettings: document.getElementById('btn-save-settings'),
    settingsTabs: document.querySelectorAll('.settings-tabs .tab'),
    
    chips: document.querySelectorAll('.chip')
};

let ws = null;
let currentCodeFiles = {};

// Auto-resize textarea
el.goalInput.addEventListener('input', function() {
    this.style.height = 'auto';
    this.style.height = (this.scrollHeight) + 'px';
});

// Setup Pipeline Nodes
const AGENT_NODES = [
    { id: 'planner', label: 'Planner', icon: 'list-todo' },
    { id: 'architect', label: 'Architect', icon: 'layout-template' },
    { id: 'test_writer', label: 'Test Writer', icon: 'test-tube' },
    { id: 'coder', label: 'Coder', icon: 'code-2' },
    { id: 'reviewer', label: 'Reviewer', icon: 'users' },
    { id: 'tester', label: 'Tester', icon: 'bug-play' },
    { id: 'fixer', label: 'Fixer', icon: 'wrench' }
];

function renderNodes() {
    el.pipelineNodes.innerHTML = AGENT_NODES.map(n => `
        <div class="node" id="node-${n.id}">
            <i data-lucide="${n.icon}"></i> ${n.label}
        </div>
    `).join('');
    lucide.createIcons();
}
renderNodes();

// UI Transitions
function submitGoal(goalText) {
    const text = goalText || el.goalInput.value.trim();
    if (!text) return;

    el.userPromptDisplay.textContent = text;
    
    // Transition UI
    el.mainContent.classList.remove('state-initial');
    el.mainContent.classList.add('state-running');
    el.chatStream.classList.remove('hidden');
    el.goalInput.value = '';
    el.goalInput.style.height = 'auto';
    
    startPipeline(text);
}

el.btnStart.addEventListener('click', () => submitGoal());
el.goalInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        submitGoal();
    }
});

el.chips.forEach(chip => {
    chip.addEventListener('click', () => {
        submitGoal(chip.textContent.trim());
    });
});

// WebSocket Handling
function updateNodeStatus(nodeId, status) {
    document.querySelectorAll('.node').forEach(n => n.classList.remove('active', 'completed', 'error'));
    const activeNode = document.getElementById(`node-${nodeId}`);
    if (activeNode) {
        activeNode.classList.add(status);
        // Scroll node into view if needed
        activeNode.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
    }
}

function appendLog(type, message) {
    const entry = document.createElement('div');
    entry.className = `log-entry ${type}`;
    const time = new Date().toLocaleTimeString([], { hour12: false });
    
    let prefix = '[System]';
    if (type === 'error') prefix = '[Error]';
    if (type === 'success') prefix = '[Success]';
    if (type === 'agent') prefix = '[Agent]';

    entry.innerHTML = `<span class="timestamp">${time}</span> <strong>${prefix}</strong> ${message}`;
    el.terminalOutput.appendChild(entry);
    el.terminalOutput.scrollTop = el.terminalOutput.scrollHeight;
}

function startPipeline(goal) {
    if (ws) ws.close();
    
    el.terminalOutput.innerHTML = '';
    appendLog('system', `Starting pipeline for goal: ${goal}`);
    
    el.pipelineBadge.textContent = "Running";
    el.pipelineBadge.className = "badge badge-running";
    
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${protocol}//${window.location.host}/api/run`);
    
    ws.onopen = () => ws.send(JSON.stringify({ goal: goal }));
    
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        
        if (data.type === 'status') {
            appendLog('system', data.message);
        } else if (data.type === 'log') {
            const l = data.log;
            appendLog(l.level === 'error' ? 'error' : (l.level === 'success' ? 'success' : 'agent'), `[${l.source}] ${l.message}`);
            // Highlight active pipeline node based on log source
            const nodeMap = { planner: 'planner', architect: 'architect', test_writer: 'test_writer', coder: 'coder', reviewer: 'reviewer', tester: 'tester', fixer: 'fixer' };
            if (nodeMap[l.source]) {
                document.querySelectorAll('.node').forEach(n => n.classList.remove('active'));
                const activeNode = document.getElementById(`node-${nodeMap[l.source]}`);
                if (activeNode) activeNode.classList.add('active');
            }
        } else if (data.type === 'update') {
            updateNodeStatus(data.node, 'completed');
            if (data.state && data.state.code) {
                currentCodeFiles = data.state.code;
                renderFileTree(currentCodeFiles);
                el.btnOpenArtifacts.classList.remove('hidden');
                openDrawer();
            }
        } else if (data.type === 'error') {
            appendLog('error', data.message);
            el.pipelineBadge.textContent = "Error";
            el.pipelineBadge.className = "badge badge-error";
        } else if (data.type === 'done') {
            appendLog('success', data.message);
            el.pipelineBadge.textContent = "Completed";
            el.pipelineBadge.className = "badge badge-success";
            document.querySelectorAll('.node').forEach(n => {
                n.classList.remove('active');
                n.classList.add('completed');
            });
        }
    };
    
    ws.onclose = () => {
        if (el.pipelineBadge.textContent === "Running") {
            el.pipelineBadge.textContent = "Disconnected";
            el.pipelineBadge.className = "badge badge-error";
            appendLog('error', "Connection closed unexpectedly.");
        }
    };
}

// Artifacts Drawer
function openDrawer() {
    el.drawer.classList.remove('hidden');
    el.btnOpenArtifacts.classList.add('hidden');
}
function closeDrawer() {
    el.drawer.classList.add('hidden');
    if (Object.keys(currentCodeFiles).length > 0) {
        el.btnOpenArtifacts.classList.remove('hidden');
    }
}
el.btnCloseDrawer.addEventListener('click', closeDrawer);
el.btnOpenArtifacts.addEventListener('click', openDrawer);

function renderFileTree(files) {
    if (!files || Object.keys(files).length === 0) return;
    
    const tree = buildTreeObject(Object.keys(files));
    el.fileTree.innerHTML = renderTreeHTML(tree, '');
    lucide.createIcons();
    
    document.querySelectorAll('.tree-item.file').forEach(item => {
        item.addEventListener('click', (e) => {
            const path = e.currentTarget.dataset.path;
            openCodeViewer(path, files[path]);
        });
    });
}

function buildTreeObject(paths) {
    const root = {};
    for (const path of paths) {
        const parts = path.split('/');
        let current = root;
        for (let i = 0; i < parts.length; i++) {
            const part = parts[i];
            if (!current[part]) {
                current[part] = i === parts.length - 1 ? null : {};
            }
            current = current[part];
        }
    }
    return root;
}

function renderTreeHTML(tree, basePath) {
    let html = '';
    const keys = Object.keys(tree).sort((a, b) => {
        const aIsDir = tree[a] !== null;
        const bIsDir = tree[b] !== null;
        if (aIsDir && !bIsDir) return -1;
        if (!aIsDir && bIsDir) return 1;
        return a.localeCompare(b);
    });
    
    for (const key of keys) {
        const isDir = tree[key] !== null;
        const fullPath = basePath ? `${basePath}/${key}` : key;
        
        if (isDir) {
            html += `
                <div>
                    <div class="tree-item folder"><i data-lucide="folder"></i> ${key}</div>
                    <div style="padding-left: 12px;">${renderTreeHTML(tree[key], fullPath)}</div>
                </div>
            `;
        } else {
            let icon = 'file';
            if (key.endsWith('.py')) icon = 'file-code-2';
            else if (key.endsWith('.md')) icon = 'file-text';
            html += `<div class="tree-item file" data-path="${fullPath}"><i data-lucide="${icon}"></i> ${key}</div>`;
        }
    }
    return html;
}

function openCodeViewer(filename, content) {
    el.codeFilename.textContent = filename;
    let lang = 'plaintext';
    if (filename.endsWith('.py')) lang = 'python';
    if (filename.endsWith('.md')) lang = 'markdown';
    if (filename.endsWith('.json')) lang = 'json';

    el.codeContent.className = `language-${lang}`;
    el.codeContent.textContent = content;
    hljs.highlightElement(el.codeContent);
    el.codeViewer.classList.remove('hidden');
}

el.btnBackTree.addEventListener('click', () => el.codeViewer.classList.add('hidden'));

el.btnCopyCode.addEventListener('click', () => {
    navigator.clipboard.writeText(el.codeContent.textContent).then(() => {
        const icon = el.btnCopyCode.querySelector('i');
        icon.setAttribute('data-lucide', 'check');
        lucide.createIcons();
        setTimeout(() => {
            icon.setAttribute('data-lucide', 'copy');
            lucide.createIcons();
        }, 2000);
    });
});

// Modals & Settings API
function openModal(modal) { modal.classList.remove('hidden'); }
function closeModal(modal) { modal.classList.add('hidden'); }

el.btnSettings.addEventListener('click', () => { loadSettings(); openModal(el.modalSettings); });
el.modalCloses.forEach(btn => btn.addEventListener('click', (e) => closeModal(e.target.closest('.modal-overlay'))));

el.settingsTabs.forEach(tab => {
    tab.addEventListener('click', () => {
        el.settingsTabs.forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.settings-content').forEach(c => c.classList.add('hidden'));
        tab.classList.add('active');
        document.getElementById(tab.dataset.target).classList.remove('hidden');
    });
});

async function loadSettings() {
    try {
        const res = await fetch('/api/config');
        const data = await res.json();
        
        el.formApiKeys.innerHTML = '';
        for (const [key, value] of Object.entries(data.keys)) {
            let displayVal = value;
            if (value && value.length > 8) displayVal = value.substring(0, 4) + '*'.repeat(16) + value.substring(value.length - 4);
            el.formApiKeys.innerHTML += `
                <div class="form-group">
                    <label>${key}</label>
                    <input type="password" name="${key}" placeholder="${displayVal ? '••••••••••••••••' : 'Not set'}">
                </div>
            `;
        }
        
        const mRes = await fetch('/api/models');
        const mData = await mRes.json();
        el.formModels.innerHTML = '';
        for (const [task, info] of Object.entries(mData.models)) {
            const options = info.chain.map(c => `<option value="${c.provider}">${c.provider} (${c.model})</option>`).join('');
            el.formModels.innerHTML += `
                <div class="form-group">
                    <label style="text-transform: capitalize;">${task} Layer</label>
                    <select name="${task}">${options}</select>
                </div>
            `;
        }
    } catch (err) { console.error(err); }
}

el.btnSaveSettings.addEventListener('click', async () => {
    try {
        const keysToUpdate = {};
        for (const [k, v] of new FormData(el.formApiKeys).entries()) if (v.trim()) keysToUpdate[k] = v;
        if (Object.keys(keysToUpdate).length > 0) await fetch('/api/config', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({keys: keysToUpdate}) });
        
        const modelsToUpdate = {};
        for (const [k, v] of new FormData(el.formModels).entries()) modelsToUpdate[k] = v;
        await fetch('/api/models', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({selections: modelsToUpdate}) });
        
        closeModal(el.modalSettings);
    } catch (err) { console.error(err); }
});

// Reset Chat
document.getElementById('btn-new-chat').addEventListener('click', () => {
    if (ws) ws.close();
    el.mainContent.classList.remove('state-running');
    el.mainContent.classList.add('state-initial');
    el.chatStream.classList.add('hidden');
    el.goalInput.value = '';
    closeDrawer();
    el.btnOpenArtifacts.classList.add('hidden');
    currentCodeFiles = {};
});