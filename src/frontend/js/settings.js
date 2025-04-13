/**
 * Settings manager handles feed management and statistics
 */
const SettingsManager = {
    // DOM Elements
    feedsList: null,
    addFeedForm: null,
    feedUrlInput: null,
    addFeedResult: null,
    feedStats: null,
    refreshFeedsButton: null,
    refreshResult: null,
    appSettingsContainer: null,
    appSettingsForm: null,
    saveSettingsButton: null,
    settingsSaveResult: null,
    
    // State
    isLoadingFeeds: false,
    isLoadingStats: false,
    isLoadingSettings: false,
    isSavingSettings: false,
    currentSettings: {},
    
    /**
     * Initialize the settings manager
     */
    init() {
        // Get DOM elements
        this.feedsList = document.getElementById('feeds-list');
        this.addFeedForm = document.getElementById('add-feed-form');
        this.feedUrlInput = document.getElementById('feed-url');
        this.addFeedResult = document.getElementById('add-feed-result');
        this.feedStats = document.getElementById('feed-stats');
        this.refreshFeedsButton = document.getElementById('refresh-feeds');
        this.refreshResult = document.getElementById('refresh-result');
        this.appSettingsContainer = document.getElementById('app-settings-container');
        
        // Add event listeners
        this.addFeedForm.addEventListener('submit', (e) => {
            e.preventDefault();
            this.addFeed();
        });
        
        this.refreshFeedsButton.addEventListener('click', () => this.refreshFeeds());
        
        // Load feeds, stats, and app settings
        this.loadFeeds();
        this.loadStats();
        this.loadSettings();
    },
    
    /**
     * Load feeds
     */
    async loadFeeds() {
        if (this.isLoadingFeeds) return;
        
        this.isLoadingFeeds = true;
        this.feedsList.innerHTML = `
            <div class="loading-indicator">
                <div class="spinner"></div>
                <p>Loading feeds...</p>
            </div>
        `;
        
        try {
            const feeds = await API.getFeeds();
            
            // Clear loading indicator
            this.feedsList.innerHTML = '';
            
            if (feeds.length === 0) {
                this.feedsList.innerHTML = `
                    <div class="empty-message">
                        <p>No feeds added yet. Add your first feed above.</p>
                    </div>
                `;
                return;
            }
            
            // Render each feed
            feeds.forEach(feed => this.renderFeed(feed));
        } catch (error) {
            console.error('Error loading feeds:', error);
            this.feedsList.innerHTML = `
                <div class="error-message">
                    <p>Failed to load feeds. Please try refreshing the page.</p>
                </div>
            `;
        } finally {
            this.isLoadingFeeds = false;
        }
    },
    
    /**
     * Render a feed item
     * @param {Object} feed - Feed data
     */
    renderFeed(feed) {
        // Get the template
        const template = document.getElementById('feed-item-template');
        const feedElement = document.importNode(template.content, true).querySelector('.feed-item');
        
        // Set feed ID as data attribute
        feedElement.dataset.id = feed.id;
        
        // Populate the feed content
        feedElement.querySelector('.feed-title').textContent = feed.title;
        
        // Set article count
        const articleCount = feedElement.querySelector('.feed-article-count');
        articleCount.textContent = `${feed.article_count || 0} articles`;
        
        // Set last update time
        const lastUpdate = feedElement.querySelector('.feed-last-update');
        if (feed.last_fetched) {
            const lastFetchedDate = new Date(feed.last_fetched * 1000);
            lastUpdate.textContent = `Updated: ${this.formatDate(lastFetchedDate)}`;
        } else {
            lastUpdate.textContent = 'Never updated';
        }
        
        // Set up delete button
        const deleteButton = feedElement.querySelector('.delete-feed-button');
        deleteButton.addEventListener('click', () => this.confirmDeleteFeed(feed));
        
        // Add to container
        this.feedsList.appendChild(feedElement);
    },
    
    /**
     * Add a new feed
     */
    async addFeed() {
        const url = this.feedUrlInput.value.trim();
        if (!url) return;
        
        // Disable form during submission
        this.feedUrlInput.disabled = true;
        this.addFeedForm.querySelector('button').disabled = true;
        this.addFeedResult.textContent = 'Adding feed...';
        this.addFeedResult.className = 'form-result';
        
        try {
            await API.addFeed(url);
            
            // Show success message
            this.addFeedResult.textContent = 'Feed added successfully!';
            this.addFeedResult.className = 'form-result success';
            
            // Clear input
            this.feedUrlInput.value = '';
            
            // Reload feeds and stats
            this.loadFeeds();
            this.loadStats();
            
            // Also update the feeds filter dropdown in the feed view
            if (typeof FeedManager !== 'undefined' && FeedManager.loadFeedsForFilter) {
                FeedManager.loadFeedsForFilter();
            }
        } catch (error) {
            console.error('Error adding feed:', error);
            this.addFeedResult.textContent = `Failed to add feed: ${error.message}`;
            this.addFeedResult.className = 'form-result error';
        } finally {
            // Re-enable form
            this.feedUrlInput.disabled = false;
            this.addFeedForm.querySelector('button').disabled = false;
            
            // Clear message after 5 seconds
            setTimeout(() => {
                this.addFeedResult.textContent = '';
                this.addFeedResult.className = 'form-result';
            }, 5000);
        }
    },
    
    /**
     * Confirm feed deletion
     * @param {Object} feed - Feed data
     */
    confirmDeleteFeed(feed) {
        if (confirm(`Are you sure you want to delete "${feed.title}"? This will also remove all articles from this feed.`)) {
            this.deleteFeed(feed.id);
        }
    },
    
    /**
     * Delete a feed
     * @param {number} feedId - Feed ID
     */
    async deleteFeed(feedId) {
        const feedElement = this.feedsList.querySelector(`.feed-item[data-id="${feedId}"]`);
        if (!feedElement) return;
        
        // Show loading state
        feedElement.style.opacity = '0.5';
        const deleteButton = feedElement.querySelector('.delete-feed-button');
        deleteButton.disabled = true;
        
        try {
            await API.deleteFeed(feedId);
            
            // Remove feed element with animation
            if ('animate' in feedElement) {
                const animation = feedElement.animate([
                    { opacity: 0.5, height: feedElement.offsetHeight + 'px' },
                    { opacity: 0, height: 0 }
                ], { duration: 300 });
                
                animation.onfinish = () => {
                    feedElement.remove();
                    
                    // Show empty message if no feeds left
                    if (this.feedsList.children.length === 0) {
                        this.feedsList.innerHTML = `
                            <div class="empty-message">
                                <p>No feeds added yet. Add your first feed above.</p>
                            </div>
                        `;
                    }
                };
            } else {
                feedElement.remove();
            }
            
            // Reload stats
            this.loadStats();
            
            // Update the feeds filter dropdown in the feed view
            if (typeof FeedManager !== 'undefined' && FeedManager.loadFeedsForFilter) {
                FeedManager.loadFeedsForFilter();
            }
        } catch (error) {
            console.error('Error deleting feed:', error);
            
            // Restore feed element
            feedElement.style.opacity = '1';
            deleteButton.disabled = false;
            
            alert(`Failed to delete feed: ${error.message}`);
        }
    },
    
    /**
     * Load statistics
     */
    async loadStats() {
        if (this.isLoadingStats) return;
        
        this.isLoadingStats = true;
        this.feedStats.innerHTML = `
            <div class="loading-indicator">
                <div class="spinner"></div>
                <p>Loading statistics...</p>
            </div>
        `;
        
        try {
            const stats = await API.getStats();
            
            // Clear loading indicator
            this.feedStats.innerHTML = '';
            
            // Render statistics
            const statItems = [
                { label: 'Total Feeds', value: stats.total_feeds || 0 },
                { label: 'Active Feeds', value: stats.active_feeds || 0 },
                { label: 'Total Articles', value: stats.total_articles || 0 },
                { label: 'Unread Articles', value: stats.unread_articles || 0 },
                { label: 'New in 24h', value: stats.new_articles_24h || 0 }
            ];
            
            statItems.forEach(item => {
                const statElement = document.createElement('div');
                statElement.className = 'stat-item';
                statElement.innerHTML = `
                    <div class="stat-value">${item.value}</div>
                    <div class="stat-label">${item.label}</div>
                `;
                this.feedStats.appendChild(statElement);
            });
        } catch (error) {
            console.error('Error loading stats:', error);
            this.feedStats.innerHTML = `
                <div class="error-message">
                    <p>Failed to load statistics. Please try refreshing the page.</p>
                </div>
            `;
        } finally {
            this.isLoadingStats = false;
        }
    },
    
    /**
     * Refresh all feeds
     */
    async refreshFeeds() {
        // Disable button during refresh
        this.refreshFeedsButton.disabled = true;
        this.refreshResult.textContent = 'Refreshing feeds...';
        this.refreshResult.className = 'form-result';
        
        try {
            await API.refreshFeeds();
            
            // Show success message
            this.refreshResult.textContent = 'Refresh started! This may take a moment.';
            this.refreshResult.className = 'form-result success';
            
            // Set a timeout to reload stats after a delay
            setTimeout(() => {
                this.loadStats();
                this.loadFeeds();
            }, 3000);
        } catch (error) {
            console.error('Error refreshing feeds:', error);
            this.refreshResult.textContent = 'Failed to refresh feeds. Please try again.';
            this.refreshResult.className = 'form-result error';
        } finally {
            // Re-enable button
            this.refreshFeedsButton.disabled = false;
            
            // Clear message after 5 seconds
            setTimeout(() => {
                this.refreshResult.textContent = '';
                this.refreshResult.className = 'form-result';
            }, 5000);
        }
    },
    
    /**
     * Format a date for display
     * @param {Date} date - Date object
     * @returns {string} - Formatted date string
     */
    formatDate(date) {
        // Use relative time when possible
        const now = new Date();
        const diffMs = now - date;
        const diffSec = Math.floor(diffMs / 1000);
        const diffMin = Math.floor(diffSec / 60);
        const diffHour = Math.floor(diffMin / 60);
        const diffDay = Math.floor(diffHour / 24);
        
        if (diffSec < 60) {
            return 'just now';
        } else if (diffMin < 60) {
            return `${diffMin}m ago`;
        } else if (diffHour < 24) {
            return `${diffHour}h ago`;
        } else if (diffDay < 7) {
            return `${diffDay}d ago`;
        } else {
            // Fall back to date string for older articles
            return date.toLocaleDateString(undefined, { 
                year: 'numeric', 
                month: 'short', 
                day: 'numeric' 
            });
        }
    },
    
    /**
     * Load application settings
     */
    async loadSettings() {
        if (this.isLoadingSettings) return;
        
        this.isLoadingSettings = true;
        
        try {
            // Show loading state
            this.appSettingsContainer.innerHTML = `
                <div class="loading-indicator">
                    <div class="spinner"></div>
                    <p>Loading application settings...</p>
                </div>
            `;
            
            // Fetch settings from API
            const settings = await API.getSettings();
            this.currentSettings = settings;
            
            // Generate form fields
            this.renderSettingsForm(settings);
        } catch (error) {
            console.error('Error loading settings:', error);
            this.appSettingsContainer.innerHTML = `
                <div class="error-message">
                    <p>Failed to load application settings. Please try refreshing the page.</p>
                </div>
            `;
        } finally {
            this.isLoadingSettings = false;
        }
    },
    
    /**
     * Render the settings form with current values
     * @param {Object} settings - Settings data
     */
    renderSettingsForm(settings) {
      // Clear previous content
      this.appSettingsContainer.innerHTML = '';
      
      // Create the form
      const form = document.createElement('form');
      form.id = 'app-settings-form';
      form.className = 'settings-form';
      
      // Settings groups and fields
      const settingsGroups = {
          'Feed Settings': [
              { key: 'update_interval', 
                label: 'Update Interval (seconds)', 
                type: 'number', 
                min: 60, 
                step: 60 },
              { key: 'max_articles_per_feed', 
                label: 'Max Articles per Feed', 
                type: 'number', 
                min: 10, 
                max: 1000 },
              { key: 'auto_cleanup_days', 
                label: 'Auto Cleanup (days)', 
                type: 'number', 
                min: 1, 
                max: 365 },
              { key: 'auto_read', 
                label: 'Auto-mark articles as read when scrolled past', 
                type: 'checkbox' }
          ],
          'AI Settings': [
              { key: 'ai_enabled', 
                label: 'Enable AI Ranking', 
                type: 'checkbox' },
              { key: 'half_time', 
                label: 'Feedback Half-life (seconds)', 
                type: 'number', 
                min: 3600 },
              { key: 'min_feedback_for_training', 
                label: 'Min Feedback for Training', 
                type: 'number', 
                min: 1 },
              { key: 'embedding_batch_size', 
                label: 'Embedding Batch Size', 
                type: 'number', 
                min: 1, 
                max: 50 }
          ]
      };
      
      // Generate form fields grouped by category
      Object.entries(settingsGroups).forEach(([groupName, fields]) => {
          const fieldset = document.createElement('fieldset');
          
          // Add group heading
          const legend = document.createElement('legend');
          legend.textContent = groupName;
          fieldset.appendChild(legend);
          
          // Add each field in this group
          fields.forEach(field => {
              const setting = settings[field.key] || { value: '', description: '' };
              const formGroup = this.createFormField(field, setting);
              fieldset.appendChild(formGroup);
          });
          
          form.appendChild(fieldset);
      });
      
      // Add submit button
      const submitGroup = document.createElement('div');
      submitGroup.className = 'form-submit';
      
      const submitButton = document.createElement('button');
      submitButton.type = 'submit';
      submitButton.className = 'primary-button';
      submitButton.id = 'save-settings-button';
      submitButton.textContent = 'Save Settings';
      
      const resultDiv = document.createElement('div');
      resultDiv.className = 'form-result';
      resultDiv.id = 'settings-save-result';
      
      submitGroup.appendChild(submitButton);
      submitGroup.appendChild(resultDiv);
      form.appendChild(submitGroup);
      
      // Add form to container
      this.appSettingsContainer.appendChild(form);
      
      // Update local references
      this.appSettingsForm = form;
      this.saveSettingsButton = submitButton;
      this.settingsSaveResult = resultDiv;
      
      // Add event listener
      this.appSettingsForm.addEventListener('submit', (e) => {
          e.preventDefault();
          this.saveSettings();
      });
    },
    
    /**
     * Create a form field for a setting
     * @param {Object} field - Field configuration
     * @param {Object} setting - Current setting value and description
     * @returns {HTMLElement} - Form group element
     */
    createFormField(field, setting) {
        const formGroup = document.createElement('div');
        formGroup.className = 'form-group';
        
        const label = document.createElement('label');
        label.htmlFor = `setting-${field.key}`;
        label.textContent = field.label;
        
        let input;
        
        if (field.type === 'checkbox') {
            // Create checkbox input
            input = document.createElement('input');
            input.type = 'checkbox';
            input.id = `setting-${field.key}`;
            input.name = field.key;
            input.checked = setting.value === 'true' || setting.value === '1' || setting.value === 'yes';
            
            // Wrap in a container for styling
            const toggleContainer = document.createElement('div');
            toggleContainer.className = 'toggle-container';
            toggleContainer.appendChild(input);
            
            const toggleLabel = document.createElement('span');
            toggleLabel.className = 'toggle-label';
            toggleLabel.textContent = field.label;
            toggleContainer.appendChild(toggleLabel);
            
            formGroup.appendChild(toggleContainer);
        } else {
            // Create standard input (text, number, etc.)
            label.className = 'form-label';
            formGroup.appendChild(label);
            
            input = document.createElement('input');
            input.type = field.type || 'text';
            input.id = `setting-${field.key}`;
            input.name = field.key;
            input.value = setting.value || '';
            input.className = 'form-input';
            
            // Add any additional attributes
            if (field.min !== undefined) input.min = field.min;
            if (field.max !== undefined) input.max = field.max;
            if (field.step !== undefined) input.step = field.step;
            
            formGroup.appendChild(input);
        }
        
        // Add description if available
        if (setting.description) {
            const description = document.createElement('div');
            description.className = 'form-description';
            description.textContent = setting.description;
            formGroup.appendChild(description);
        }
        
        return formGroup;
    },
    
    /**
     * Save settings from form
     */
    async saveSettings() {
        if (this.isSavingSettings) return;
        
        this.isSavingSettings = true;
        this.saveSettingsButton.disabled = true;
        this.settingsSaveResult.textContent = 'Saving settings...';
        this.settingsSaveResult.className = 'form-result';
        
        try {
            // Collect values from form
            const formData = new FormData(this.appSettingsForm);
            const updatedSettings = {};
            
            // Process form data
            for (const [key, value] of formData.entries()) {
                updatedSettings[key] = value;
            }
            
            // Process checkboxes separately (since unchecked ones don't submit)
            this.appSettingsForm.querySelectorAll('input[type="checkbox"]').forEach(checkbox => {
                updatedSettings[checkbox.name] = checkbox.checked ? 'true' : 'false';
            });
            
            // Update each setting via API
            const savePromises = Object.entries(updatedSettings).map(([key, value]) => {
                return API.updateSetting(key, value);
            });
            
            await Promise.all(savePromises);
            
            // Show success message
            this.settingsSaveResult.textContent = 'Settings saved successfully!';
            this.settingsSaveResult.className = 'form-result success';
            
            // Reload settings to get the latest values
            await this.loadSettings();
        } catch (error) {
            console.error('Error saving settings:', error);
            this.settingsSaveResult.textContent = 'Failed to save settings. Please try again.';
            this.settingsSaveResult.className = 'form-result error';
        } finally {
            this.isSavingSettings = false;
            this.saveSettingsButton.disabled = false;
            
            // Clear message after 5 seconds
            setTimeout(() => {
                this.settingsSaveResult.textContent = '';
                this.settingsSaveResult.className = 'form-result';
            }, 5000);
        }
    }
};
