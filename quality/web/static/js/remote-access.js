document.addEventListener('DOMContentLoaded', function() {
    // Create remote access indicator
    const header = document.querySelector('header');
    const remoteAccessInfo = document.createElement('div');
    remoteAccessInfo.className = 'remote-access-info';
    remoteAccessInfo.innerHTML = '<span>Checking remote access status...</span>';
    header.appendChild(remoteAccessInfo);
    
    // Function to fetch remote access status
    function checkRemoteAccess() {
        fetch('/remote_access')
            .then(response => response.json())
            .then(data => {
                if (data.status === 'active' && data.tunnel_url !== 'Not available') {
                    remoteAccessInfo.innerHTML = `
                        <div class="remote-link">
                            <span>Remote Access:</span>
                            <a href="${data.tunnel_url}" target="_blank">${data.tunnel_url}</a>
                            <a href="https://chart.googleapis.com/chart?cht=qr&chs=300x300&chl=${data.tunnel_url}" 
                               target="_blank" class="qr-icon" title="Show QR Code">📱</a>
                        </div>
                    `;
                    remoteAccessInfo.classList.add('active');
                } else {
                    remoteAccessInfo.innerHTML = '<span>Remote access not available</span>';
                    remoteAccessInfo.classList.add('inactive');
                }
            })
            .catch(error => {
                console.error('Error checking remote access:', error);
                remoteAccessInfo.innerHTML = '<span>Error checking remote access</span>';
                remoteAccessInfo.classList.add('error');
            });
    }
    
    // Check remote access status immediately and then every 30 seconds
    checkRemoteAccess();
    setInterval(checkRemoteAccess, 30000);
});
