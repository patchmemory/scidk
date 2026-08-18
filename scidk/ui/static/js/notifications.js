/**
 * Browser notification system for SciDK alerts
 */

class NotificationManager {
    constructor() {
        this.permission = Notification.permission;
        this.enabled = localStorage.getItem('scidk_notifications_enabled') === 'true';
    }

    /**
     * Check if browser notifications are supported
     */
    isSupported() {
        return 'Notification' in window;
    }

    /**
     * Request permission from user
     */
    async requestPermission() {
        if (!this.isSupported()) {
            return false;
        }

        if (this.permission === 'granted') {
            return true;
        }

        try {
            const permission = await Notification.requestPermission();
            this.permission = permission;

            if (permission === 'granted') {
                this.enabled = true;
                localStorage.setItem('scidk_notifications_enabled', 'true');
                return true;
            }
            return false;
        } catch (error) {
            console.error('Error requesting notification permission:', error);
            return false;
        }
    }

    /**
     * Show a browser notification
     */
    show(title, options = {}) {
        if (!this.isSupported() || this.permission !== 'granted' || !this.enabled) {
            return null;
        }

        const defaultOptions = {
            icon: '/static/icon-192.png',
            badge: '/static/badge-72.png',
            tag: 'scidk-alert',
            requireInteraction: false,
            ...options
        };

        try {
            const notification = new Notification(title, defaultOptions);

            // Auto-close after 10 seconds if not requiring interaction
            if (!defaultOptions.requireInteraction) {
                setTimeout(() => notification.close(), 10000);
            }

            // Click handler - focus window and navigate to alerts
            notification.onclick = () => {
                window.focus();
                if (options.url) {
                    window.location.href = options.url;
                } else {
                    window.location.href = '/#alerts';
                }
                notification.close();
            };

            return notification;
        } catch (error) {
            console.error('Error showing notification:', error);
            return null;
        }
    }

    /**
     * Enable browser notifications
     */
    async enable() {
        const granted = await this.requestPermission();
        if (granted) {
            this.enabled = true;
            localStorage.setItem('scidk_notifications_enabled', 'true');
            return true;
        }
        return false;
    }

    /**
     * Disable browser notifications
     */
    disable() {
        this.enabled = false;
        localStorage.setItem('scidk_notifications_enabled', 'false');
    }

    /**
     * Get current status
     */
    getStatus() {
        return {
            supported: this.isSupported(),
            permission: this.permission,
            enabled: this.enabled
        };
    }
}

// Global instance
window.scidkNotifications = new NotificationManager();

// Poll for new alerts (checks every 30 seconds)
let alertPollingInterval = null;
let lastAlertCheck = Date.now();

async function checkForNewAlerts() {
    try {
        const response = await fetch('/api/settings/alerts/history?limit=10');
        if (!response.ok) return;

        const data = await response.json();
        const alerts = data.history || [];

        // Show notifications for new alerts since last check
        alerts.forEach(alert => {
            const alertTime = new Date(alert.triggered_at_iso).getTime();
            if (alertTime > lastAlertCheck && alert.success) {
                // Show browser notification
                const details = alert.condition_details || {};
                const body = Object.entries(details)
                    .filter(([k]) => k !== 'test')
                    .map(([k, v]) => `${k}: ${v}`)
                    .join('\n');

                window.scidkNotifications.show(
                    `Alert: ${alert.alert_name || 'Unknown Alert'}`,
                    {
                        body: body || 'Alert triggered',
                        icon: '/static/icon-192.png',
                        tag: `alert-${alert.id}`,
                        url: '/#alerts'
                    }
                );
            }
        });

        lastAlertCheck = Date.now();
    } catch (error) {
        console.error('Error checking for alerts:', error);
    }
}

// Start polling when notifications are enabled
function startAlertPolling() {
    if (alertPollingInterval) return;

    // Check immediately
    checkForNewAlerts();

    // Then check every 30 seconds
    alertPollingInterval = setInterval(checkForNewAlerts, 30000);
}

function stopAlertPolling() {
    if (alertPollingInterval) {
        clearInterval(alertPollingInterval);
        alertPollingInterval = null;
    }
}

// Auto-start polling if notifications are enabled
if (window.scidkNotifications.enabled && window.scidkNotifications.permission === 'granted') {
    startAlertPolling();
}

// Export for use in UI
window.startAlertPolling = startAlertPolling;
window.stopAlertPolling = stopAlertPolling;
