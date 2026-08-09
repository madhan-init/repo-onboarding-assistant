let currentRepoId = null;
let pollInterval = null;
const API_BASE = window.API_BASE || '';

const langColors = {
    '.py': '#3572A5',
    '.js': '#f1e05a',
    '.ts': '#3178c6',
    '.html': '#e34c26',
    '.css': '#563d7c',
    '.md': '#083fa1',
    '.go': '#00ADD8'
};
const defaultColor = '#8b949e';

document.getElementById('indexForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    let url = document.getElementById('repoUrl').value.trim();
    if (!url) return;
    if (!url.startsWith('http')) {
        url = 'https://github.com/' + url;
    }

    resetUI();
    const indexBtn = document.getElementById('indexBtn');
    if (indexBtn) indexBtn.disabled = true;

    updateStatus('Indexing repository...', 'pulse');

    try {
        const res = await fetch(`${API_BASE}/index`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({github_url: url})
        });
        const data = await res.json();
        if (res.ok) {
            currentRepoId = data.repo_id;
            startPolling();
        } else {
            showError(data.detail || 'Failed to start indexing');
        }
    } catch (err) {
        showError(err.message);
    }
});

function startPolling() {
    if (pollInterval) clearInterval(pollInterval);
    pollInterval = setInterval(async () => {
        try {
            const res = await fetch(`${API_BASE}/overview/${currentRepoId}`);
            const data = await res.json();
            
            if (data.status === 'ready') {
                clearInterval(pollInterval);
                updateStatus('Indexing complete', 'check');
                renderRepoData(data);
            } else if (data.status === 'failed') {
                clearInterval(pollInterval);
                showError('Indexing failed. Check server logs.');
            } else {
                updateStatus('Indexing repository...', 'pulse');
            }
        } catch (err) {
            clearInterval(pollInterval);
            showError(err.message);
        }
    }, 2000);
}

function updateStatus(text, type) {
    const statusDiv = document.getElementById('headerStatus');
    let icon = '';
    if (type === 'pulse') icon = '<div class="pulse-dot"></div>';
    else if (type === 'check') icon = '<svg class="check-icon" height="16" viewBox="0 0 16 16" width="16" fill="currentColor"><path d="M13.78 4.22a.75.75 0 0 1 0 1.06l-7.25 7.25a.75.75 0 0 1-1.06 0L2.22 9.28a.751.751 0 0 1 .018-1.042.751.751 0 0 1 1.042-.018L6 10.94l6.72-6.72a.75.75 0 0 1 1.06 0Z"></path></svg>';
    statusDiv.innerHTML = `${icon}<span>${text}</span>`;
}

function showError(msg) {
    const indexBtn = document.getElementById('indexBtn');
    if (indexBtn) indexBtn.disabled = false;
    updateStatus('Failed', 'error');
    document.getElementById('loadingState').style.display = 'none';
    document.getElementById('repoContent').style.display = 'block';
    document.getElementById('emptyState').style.display = 'none';
    document.getElementById('chatThread').innerHTML = `
        <div class="error-callout">
            <strong>Error:</strong> ${msg}
        </div>
    `;
}

function resetUI() {
    document.getElementById('emptyState').style.display = 'none';
    document.getElementById('repoContent').style.display = 'none';
    document.getElementById('loadingState').style.display = 'flex';
    document.getElementById('chatThread').innerHTML = '';
    document.getElementById('fileTree').innerHTML = '';
}

function getExt(filename) {
    const idx = filename.lastIndexOf('.');
    return idx > 0 ? filename.substring(idx) : '';
}

function renderRepoData(data) {
    const indexBtn = document.getElementById('indexBtn');
    if (indexBtn) indexBtn.disabled = false;
    document.getElementById('emptyState').style.display = 'none';
    document.getElementById('loadingState').style.display = 'none';
    document.getElementById('repoContent').style.display = 'flex';
    
    let overview = data.overview_text || 'No overview available.';
    overview = overview.replace(/\*\*/g, '');
    document.getElementById('overviewText').textContent = overview;
    
    // File tree
    const treeDiv = document.getElementById('fileTree');
    treeDiv.innerHTML = '';
    (data.folder_tree || []).forEach(file => {
        const ext = getExt(file);
        const color = langColors[ext] || defaultColor;
        const fileDiv = document.createElement('div');
        fileDiv.className = 'file-item';
        fileDiv.title = file;
        fileDiv.innerHTML = `
            <div class="lang-dot" style="background-color: ${color}"></div>
            <span>${file}</span>
        `;
        fileDiv.onclick = () => openFileViewer(file);
        treeDiv.appendChild(fileDiv);
    });

    // Language bar
    const total = Object.values(data.language_counts || {}).reduce((a, b) => a + b, 0);
    let barHtml = '';
    let legendHtml = '';
    
    if (total > 0) {
        for (const [lang, count] of Object.entries(data.language_counts)) {
            const pct = (count / total) * 100;
            const color = langColors[lang] || defaultColor;
            barHtml += `<div class="language-segment" style="width: ${pct}%; background-color: ${color};" title="${lang}"></div>`;
            legendHtml += `<div class="legend-item"><div class="lang-dot" style="background-color: ${color}"></div>${lang} <span style="color:var(--text-muted);font-weight:normal">${pct.toFixed(1)}%</span></div>`;
        }
    }
    document.getElementById('languageBar').innerHTML = barHtml;
    document.getElementById('languageLegend').innerHTML = legendHtml;
}

// Chat
document.getElementById('askForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!currentRepoId) return;
    
    const input = document.getElementById('questionInput');
    const question = input.value.trim();
    if (!question) return;
    
    input.value = '';
    appendMessage('You', question);
    
    const btn = document.getElementById('askBtn');
    btn.disabled = true;
    btn.textContent = 'Thinking...';
    
    try {
        const res = await fetch(`${API_BASE}/ask`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({repo_id: currentRepoId, question: question})
        });
        const data = await res.json();
        
        if (res.ok) {
            appendMessage('Assistant', formatAnswer(data.answer, data.citations));
        } else {
            appendMessage('Error', data.detail || 'Failed to ask question');
        }
    } catch (err) {
        appendMessage('Error', err.message);
    } finally {
        btn.disabled = false;
        btn.textContent = 'Ask';
        window.scrollTo(0, document.body.scrollHeight);
    }
});

function appendMessage(sender, htmlContent) {
    const time = new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
    
    const html = `
        <div class="chat-message">
            <div class="chat-card">
                <div class="chat-header">
                    <strong>${sender}</strong> commented <span style="float:right">${time}</span>
                </div>
                <div class="chat-body">
                    ${htmlContent}
                </div>
            </div>
        </div>
    `;
    
    document.getElementById('chatThread').insertAdjacentHTML('beforeend', html);
}

function formatAnswer(text, citations = []) {
    // Escape HTML first
    let formatted = text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    
    // Replace [filename:start-end] with styled citation pills
    const citationRegex = /\[([^:]+):(\d+)-(\d+)\]/g;
    formatted = formatted.replace(citationRegex, (match, file, start, end) => {
        return `<span class="citation" data-file="${file}" title="Lines ${start}-${end} in ${file}">${file}:${start}-${end}</span>`;
    });
    
    // Convert newlines to breaks
    formatted = formatted.replace(/\n/g, '<br>');
    
    // Format inline code
    formatted = formatted.replace(/`([^`]+)`/g, '<code style="background:rgba(240,246,252,0.15);padding:2px 4px;border-radius:4px;font-family:var(--font-code);font-size:13px;">$1</code>');
    
    // Format bold text
    formatted = formatted.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    
    return formatted;
}

// Popover logic
const popover = document.getElementById('citationPopover');
const popoverHeader = document.getElementById('popoverHeader');
const popoverContent = document.getElementById('popoverContent');

document.addEventListener('mouseover', async (e) => {
    if (e.target.classList.contains('citation')) {
        const file = e.target.getAttribute('data-file');
        
        popoverHeader.textContent = `Loading ${file}...`;
        popoverContent.textContent = '';
        popover.style.display = 'block';
        
        const rect = e.target.getBoundingClientRect();
        popover.style.top = (rect.bottom + window.scrollY + 5) + 'px';
        popover.style.left = Math.max(10, rect.left + window.scrollX - 100) + 'px';
        
        try {
            const res = await fetch(`/snippet/${currentRepoId}?file_path=${encodeURIComponent(file)}`);
            const data = await res.json();
            popoverHeader.textContent = file;
            popoverContent.textContent = data.content || 'Snippet not found';
        } catch (err) {
            popoverHeader.textContent = 'Error loading snippet';
        }
    }
});

document.addEventListener('mouseout', (e) => {
    if (e.target.classList.contains('citation')) {
        popover.style.display = 'none';
    }
});

// Resizer logic
const sidebar = document.getElementById('sidebar');
const resizer = document.getElementById('resizer');
const chatInputContainer = document.querySelector('.chat-input-container');

let isResizing = false;

if (resizer && sidebar) {
    resizer.addEventListener('mousedown', (e) => {
        e.preventDefault(); // Prevent text selection
        isResizing = true;
        resizer.classList.add('resizing');
        document.body.style.cursor = 'ew-resize';
        document.body.style.userSelect = 'none';
    });

    document.addEventListener('mousemove', (e) => {
        if (!isResizing) return;
        
        let newWidth = e.clientX;
        if (newWidth < 200) newWidth = 200;
        if (newWidth > window.innerWidth * 0.6) newWidth = window.innerWidth * 0.6;
        
        sidebar.style.width = `${newWidth}px`;
    });

    document.addEventListener('mouseup', () => {
        if (isResizing) {
            isResizing = false;
            resizer.classList.remove('resizing');
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
        }
    });
}

// File Viewer Modal Logic
const fileModal = document.getElementById('fileViewerModal');
const closeFileModal = document.getElementById('closeFileViewer');

closeFileModal.onclick = () => {
    fileModal.style.display = 'none';
};

window.addEventListener('click', (e) => {
    if (e.target === fileModal) {
        fileModal.style.display = 'none';
    }
});

async function openFileViewer(filePath) {
    if (!currentRepoId) return;
    
    document.getElementById('fileViewerTitle').textContent = filePath;
    document.getElementById('fileViewerContent').textContent = 'Loading...';
    fileModal.style.display = 'flex';
    
    try {
        const res = await fetch(`${API_BASE}/file/${currentRepoId}?file_path=${encodeURIComponent(filePath)}`);
        const data = await res.json();
        document.getElementById('fileViewerContent').textContent = data.content || 'File content not found.';
    } catch (err) {
        document.getElementById('fileViewerContent').textContent = 'Error loading file content.';
    }
}
