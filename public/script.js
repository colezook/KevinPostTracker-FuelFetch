document.getElementById('clearPosts').addEventListener('click', clearPosts);
document.getElementById('runMain').addEventListener('click', runMain);
document.getElementById('runCustom').addEventListener('click', runCustom);

async function clearPosts() {
    try {
        const response = await fetch('/clear-posts', { method: 'POST' });
        const data = await response.json();
        if (data.success) {
            document.getElementById('output').innerText = data.message;
        } else {
            throw new Error(data.error || 'Unknown error occurred');
        }
    } catch (error) {
        console.error('Error:', error);
        document.getElementById('output').innerText = `Failed to clear posts table: ${error.message}`;
    }
}

async function runMain() {
    try {
        const response = await fetch('/run-main', { method: 'POST' });
        const data = await response.json();
        document.getElementById('output').innerText = data.message + '\n' + data.output;
    } catch (error) {
        console.error('Error:', error);
        document.getElementById('output').innerText = 'Failed to run main post processing';
    }
}

async function runCustom() {
    const userIdsText = document.getElementById('userIds').value;
    const userIds = userIdsText.split('\n').map(id => id.trim()).filter(id => id);

    if (userIds.length === 0) {
        document.getElementById('output').innerText = 'Please enter at least one user ID';
        return;
    }

    try {
        const response = await fetch('/run-custom', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ userIds }),
        });
        const data = await response.json();
        document.getElementById('output').innerText = data.message + '\n' + data.output;
    } catch (error) {
        console.error('Error:', error);
        document.getElementById('output').innerText = 'Failed to run custom post processing';
    }
}
