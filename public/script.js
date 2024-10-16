document.getElementById('clearPosts').addEventListener('click', clearPosts);
document.getElementById('runMain').addEventListener('click', runMain);
document.getElementById('runCustom').addEventListener('click', runCustom);

const output = document.getElementById('output');

function appendToOutput(text, type = 'output') {
    const line = document.createElement('div');
    line.textContent = text;
    line.className = type === 'error' ? 'text-red-500' : (type === 'info' ? 'text-yellow-500' : 'text-white');
    output.appendChild(line);
    output.scrollTop = output.scrollHeight;
}

async function clearPosts() {
    try {
        const response = await fetch('/clear-posts', { method: 'POST' });
        const contentType = response.headers.get("content-type");
        if (contentType && contentType.indexOf("application/json") !== -1) {
            const data = await response.json();
            if (data.success) {
                appendToOutput(data.message, 'info');
            } else {
                throw new Error(data.error || 'Unknown error occurred');
            }
        } else {
            const text = await response.text();
            throw new Error(`Unexpected response: ${text.substring(0, 100)}...`);
        }
    } catch (error) {
        console.error('Error:', error);
        appendToOutput(`Failed to clear posts table: ${error.message}`, 'error');
    }
}

function runMain() {
    output.innerHTML = '';
    const eventSource = new EventSource('/run-main');
    
    eventSource.onmessage = function(event) {
        const data = JSON.parse(event.data);
        appendToOutput(data.message, data.type);
    };
    
    eventSource.onerror = function(event) {
        console.error("EventSource failed:", event);
        eventSource.close();
    };
}

function runCustom() {
    const userIdsText = document.getElementById('userIds').value;
    const userIds = userIdsText.split('\n').map(id => id.trim()).filter(id => id);

    if (userIds.length === 0) {
        appendToOutput('Please enter at least one user ID', 'error');
        return;
    }

    output.innerHTML = '';
    const eventSource = new EventSource(`/run-custom?userIds=${userIds.join(',')}`);
    
    eventSource.onmessage = function(event) {
        const data = JSON.parse(event.data);
        appendToOutput(data.message, data.type);
    };
    
    eventSource.onerror = function(event) {
        console.error("EventSource failed:", event);
        eventSource.close();
    };
}

// Connect to SSE for real-time console output
const consoleEventSource = new EventSource('/events');

consoleEventSource.onmessage = function(event) {
    const data = JSON.parse(event.data);
    appendToOutput(data.message, data.type);
};

consoleEventSource.onerror = function(event) {
    console.error("Console EventSource failed:", event);
    consoleEventSource.close();
};
