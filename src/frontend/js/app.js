/**
 * Main application module
 */
const App = {
    // DOM Elements
    feedButton: null,
    settingsButton: null,
    feedView: null,
    settingsView: null,
    
    // Current active view
    currentView: 'feed',
    
    /**
     * Initialize the application
     */
    init() {
        // Get DOM elements
        this.feedButton = document.getElementById('feed-button');
        this.settingsButton = document.getElementById('settings-button');
        this.feedView = document.getElementById('feed-view');
        this.settingsView = document.getElementById('settings-view');
        
        // Add event listeners for navigation
        this.feedButton.addEventListener('click', () => this.switchView('feed'));
        this.settingsButton.addEventListener('click', () => this.switchView('settings'));
        
        // Initialize managers
        FeedManager.init();
        SettingsManager.init();
        AppSettingsManager.init();
        
        // Check for hash in URL for direct navigation
        this.checkUrlHash();
        
        // Listen for hash changes
        window.addEventListener('hashchange', () => this.checkUrlHash());
        
        // Add service worker for offline support if supported
        this.registerServiceWorker();
    },
    
    /**
     * Switch between views
     * @param {string} viewName - Name of view to switch to
     */
    switchView(viewName) {
        if (viewName === this.currentView) return;
        
        // Update navigation buttons
        this.feedButton.classList.toggle('active', viewName === 'feed');
        this.settingsButton.classList.toggle('active', viewName === 'settings');
        
        // Update views
        this.feedView.classList.toggle('active', viewName === 'feed');
        this.settingsView.classList.toggle('active', viewName === 'settings');
        
        // Update URL hash without triggering a page reload
        history.replaceState(null, null, viewName === 'feed' ? '#feed' : '#settings');
        
        // Update current view
        this.currentView = viewName;
    },
    
    /**
     * Check URL hash for direct navigation
     */
    checkUrlHash() {
        const hash = window.location.hash.substring(1);
        if (hash === 'settings') {
            this.switchView('settings');
        } else {
            // Default to feed view
            this.switchView('feed');
        }
    },
    
    /**
     * Register service worker for offline support
     */
    registerServiceWorker() {
        if ('serviceWorker' in navigator) {
            window.addEventListener('load', () => {
                navigator.serviceWorker.register('/sw.js').then(registration => {
                    console.log('ServiceWorker registration successful with scope:', registration.scope);
                }).catch(error => {
                    console.log('ServiceWorker registration failed:', error);
                });
            });
        }
    }
};

// Initialize the app when DOM is ready
document.addEventListener('DOMContentLoaded', () => App.init());
