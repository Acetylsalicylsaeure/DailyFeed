/**
 * App settings manager handles global application settings
 */
const AppSettingsManager = {
    // DOM Elements
    settingsContainer: null,
    settingsForm: null,
    saveSettingsButton: null,
    settingsSaveResult: null,
    
    // State
    isLoadingSettings: false,
    isSavingSettings: false,
    currentSettings: {},
    
    /**
     * Initialize the app settings manager
     */
    init() {
        // Get DOM elements
        this.settingsContainer = document.getElementById('app-settings-container');
        this.settingsForm = document.getElementById('app-settings-form');
        this.saveSettingsButton = document.getElementById('save-settings-button');
        this.settingsSaveResult = document.getElementById('settings-save-result');
        
        // Add event listeners
        this.settingsForm.addEventListener('submit', (e) => {
            e.preventDefault();
            this.saveSettings();
        });
        
        // Load settings
        this.loadSettings();
    },
    
    /**
     * Load application settings
     */
    async loadSettings() {
        if (this.isLoadingSettings) return;
        
        this.isLoadingSettings = true;
        
        try {
            // Show loading state
            this.settingsContainer.innerHTML = `
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
            this.settingsContainer.innerHTML = `
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
        this.settingsContainer.innerHTML = '';
        
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
                  max: 365 }
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
        this.settingsContainer.appendChild(form);
        
        // Update local references
        this.settingsForm = form;
        this.saveSettingsButton = submitButton;
        this.settingsSaveResult = resultDiv;
        
        // Add event listener
        this.settingsForm.addEventListener('submit', (e) => {
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
            const formData = new FormData(this.settingsForm);
            const updatedSettings = {};
            
            // Process form data
            for (const [key, value] of formData.entries()) {
                updatedSettings[key] = value;
            }
            
            // Process checkboxes separately (since unchecked ones don't submit)
            this.settingsForm.querySelectorAll('input[type="checkbox"]').forEach(checkbox => {
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
