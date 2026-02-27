import {
    settingsForm,
    addContextRuleBtn,
    addMeetingDateCheckbox,
    meetingDateSourceGroup,
    meetingNameTemplatesContainer,
    confirmPromptOnActionCheckbox,
    addMeetingNameTemplateBtn,
    contextRulesContainer,
    promptPreviewContainer,
    promptPreviewContent,
} from '../dom.js';

import { getSettingsFromDOM } from '../utils/helpers.js';

let settings = {};

function addContextRuleRow(pattern = '', prompt = '', isEnabled = true, container, onUpdate) {
    const ruleItem = document.createElement('div');
    ruleItem.className = 'context-rule-item';

    ruleItem.innerHTML = `
        <div class="context-rule-header">
            <label class="context-rule-toggle">
                <input type="checkbox" class="context-rule-enabled" ${isEnabled ? 'checked' : ''}>
                Включено
            </label>
            <input type="text" class="context-rule-pattern input-field" placeholder="Шаблон файла (e.g. *.html)" value="${pattern}">
            <button type="button" class="action-btn remove-rule-btn">&times;</button>
        </div>
        <textarea class="context-rule-prompt" rows="8" placeholder="Добавка к промпту...">${prompt}</textarea>
    `;

    ruleItem.querySelector('.remove-rule-btn').addEventListener('click', () => {
        ruleItem.remove();
        onUpdate();
    });

    ruleItem.querySelector('.context-rule-enabled').addEventListener('change', onUpdate);
    ruleItem.querySelector('.context-rule-pattern').addEventListener('input', onUpdate);
    ruleItem.querySelector('.context-rule-prompt').addEventListener('input', onUpdate);

    container.appendChild(ruleItem);
    return ruleItem;
}

function renderContextFileRules(rules = []) {
    if (!contextRulesContainer) return;
    contextRulesContainer.innerHTML = '';
    if (rules && rules.length > 0) {
        rules.forEach(rule => {
            addContextRuleRow(rule.pattern, rule.prompt, rule.enabled, contextRulesContainer, () => saveSettings(['context_file_rules']).then(updatePromptPreview));
        });
    } else {
        addContextRuleRow('', '', true, contextRulesContainer, () => saveSettings(['context_file_rules']).then(updatePromptPreview));
    }
}

async function updatePromptPreview() {
    if (!promptPreviewContainer) return;
    try {
        const response = await fetch('/preview_prompt_addition', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(getSettingsFromDOM(document)) });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        if (data.prompt_text) {
            promptPreviewContent.textContent = data.prompt_text;
            promptPreviewContainer.style.display = 'block';
        } else {
            promptPreviewContainer.style.display = 'none';
        }
    } catch (error) { console.error('Error fetching prompt preview:', error); }
}

function createMeetingNameTemplateRow(template, activeId, isEditable) {
    const item = document.createElement('div');
    item.className = 'meeting-name-template-item';
    item.dataset.id = template.id;

    const radioId = `template-radio-${template.id}`;
    const isChecked = template.id === activeId || (activeId === null && template.id === 'null');

    item.innerHTML = `
        <input type="radio" id="${radioId}" name="active_meeting_name_template" value="${template.id}" ${isChecked ? 'checked' : ''}>
        <label for="${radioId}" class="meeting-name-template-label"></label>
    `;

    const label = item.querySelector('label');
    if (isEditable) {
        label.innerHTML = `
            <input type="text" class="meeting-name-template-input input-field" value="${template.template}">
            <button type="button" class="action-btn remove-rule-btn">&times;</button>
        `;
        const input = label.querySelector('input');
        const removeBtn = label.querySelector('button');

        input.addEventListener('input', () => { saveSettings(['meeting_name_templates']).then(updatePromptPreview); });
        removeBtn.addEventListener('click', (e) => {
            e.preventDefault();
            item.remove();
            saveSettings(['meeting_name_templates']).then(updatePromptPreview);
        });
    } else {
        label.textContent = template.template;
    }

    item.querySelector('input[type="radio"]').addEventListener('change', () => { saveSettings(['active_meeting_name_template_id']).then(updatePromptPreview); });

    return item;
}

function renderMeetingNameTemplates(templates = [], activeId = null) {
    if (!meetingNameTemplatesContainer) return;
    meetingNameTemplatesContainer.innerHTML = '';

    const noneOption = createMeetingNameTemplateRow({ id: 'null', template: 'Не добавлять' }, activeId, false);
    meetingNameTemplatesContainer.appendChild(noneOption);

    templates.forEach(template => {
        const templateRow = createMeetingNameTemplateRow(template, activeId, true);
        meetingNameTemplatesContainer.appendChild(templateRow);
    });
}

async function saveSettings(keysToSave = null) {
    const currentSettings = getSettingsFromDOM(document);
    
    let settingsToSave = currentSettings;
    if (Array.isArray(keysToSave)) {
        settingsToSave = {};
        for (const key of keysToSave) {
            if (key in currentSettings) {
                settingsToSave[key] = currentSettings[key];
            }
        }
    }

    await fetch('/save_web_settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settingsToSave)
    });
}

function toggleMeetingDateSourceVisibility() { 
    if (meetingDateSourceGroup) {
        const isEnabled = addMeetingDateCheckbox.checked;
        const radios = meetingDateSourceGroup.querySelectorAll('input[name="meeting_date_source"]');
        const labels = meetingDateSourceGroup.querySelectorAll('label');

        radios.forEach(radio => {
            radio.disabled = !isEnabled;
        });

        labels.forEach(label => {
            label.style.color = isEnabled ? '' : '#aaa'; // Делаем текст серым, когда опция отключена
        });
    }
}

export async function loadSettings() {
    const response = await fetch('/get_web_settings');
    settings = await response.json();
    
    const useCustomPrompt = document.getElementById('use-custom-prompt');
    if(useCustomPrompt) useCustomPrompt.checked = settings.use_custom_prompt;

    const promptAddition = document.getElementById('prompt-addition');
    if(promptAddition) promptAddition.value = settings.prompt_addition;

    if(addMeetingDateCheckbox) addMeetingDateCheckbox.checked = settings.add_meeting_date;

    const dateSourceRadio = document.querySelector(`input[name="meeting_date_source"][value="${settings.meeting_date_source}"]`);
    if (dateSourceRadio) dateSourceRadio.checked = true;

    if(confirmPromptOnActionCheckbox) confirmPromptOnActionCheckbox.checked = settings.confirm_prompt_on_action;

    renderMeetingNameTemplates(settings.meeting_name_templates, settings.active_meeting_name_template_id);
    toggleMeetingDateSourceVisibility();
    renderContextFileRules(settings.context_file_rules);
    updatePromptPreview();
}

export function initSettings(container = document, onUpdate = null) {
    const isModal = container !== document;
    const form = container.querySelector(isModal ? '#modal-settings-tab' : '#settings-form');
    if (!form) return;

    const updateCallback = onUpdate || (() => saveSettings().then(updatePromptPreview));

    if (!isModal) {
        loadSettings();

        form.querySelector('#use-custom-prompt')?.addEventListener('change', () => { saveSettings(['use_custom_prompt']).then(updatePromptPreview); });
        form.querySelector('#prompt-addition')?.addEventListener('input', () => { saveSettings(['prompt_addition']).then(updatePromptPreview); });
        form.querySelector('#add-meeting-date')?.addEventListener('change', () => {
            toggleMeetingDateSourceVisibility();
            saveSettings(['add_meeting_date']).then(updatePromptPreview);
        });
        form.querySelectorAll('input[name="meeting_date_source"]').forEach(radio => {
            radio.addEventListener('change', () => { saveSettings(['meeting_date_source']).then(updatePromptPreview); });
        });
        form.querySelector('#confirm-prompt-on-action')?.addEventListener('change', () => { saveSettings(['confirm_prompt_on_action']).then(updatePromptPreview); });

        form.addEventListener('submit', (e) => e.preventDefault());
    }

    const localPromptPreviewContainer = container.querySelector(isModal ? '#modal-preview-col' : '#prompt-preview-container');
    if (localPromptPreviewContainer && !isModal) {
        const header = localPromptPreviewContainer.querySelector('h4');
        if (header) {
            header.insertAdjacentHTML('afterbegin', '<span class="expand-icon"></span>');
            localPromptPreviewContainer.classList.add('collapsed');
            header.addEventListener('click', () => {
                localPromptPreviewContainer.classList.toggle('collapsed');
            });
        }
    }

    form.querySelectorAll('.settings-group-header').forEach(header => {
        header.addEventListener('click', () => {
            const group = header.closest('.settings-group');
            if (group) group.classList.toggle('collapsed');
        });
    });
    
    const localContextRulesContainer = form.querySelector(isModal ? '#modal-settings-tab #context-file-rules-container' : '#context-file-rules-container');
    form.querySelector(isModal ? '#modal-settings-tab #add-context-rule-btn' : '#add-context-rule-btn')?.addEventListener('click', () => {
        addContextRuleRow('', '', true, localContextRulesContainer, updateCallback);
    });

    const localMeetingNameTemplatesContainer = form.querySelector(isModal ? '#modal-settings-tab #meeting-name-templates-container' : '#meeting-name-templates-container');
    form.querySelector(isModal ? '#modal-settings-tab #add-meeting-name-template-btn' : '#add-meeting-name-template-btn')?.addEventListener('click', () => {
        const newId = `template-${Date.now()}`;
        const newTemplate = { id: newId, template: '' };
        const newRow = createMeetingNameTemplateRow(newTemplate, null, true); // onUpdate is handled by event delegation in modal
        localMeetingNameTemplatesContainer.appendChild(newRow);
        newRow.querySelector('.meeting-name-template-input').focus();
    });
}

export async function getSettings() {
    const response = await fetch('/get_web_settings');
    return await response.json();
}

export { updatePromptPreview };
