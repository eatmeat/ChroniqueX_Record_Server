import { modal, modalConfirmBtn, modalCancelBtn, modalSettingsCol, modalContactsCol, modalPreviewCol, recreateModal } from '../dom.js';
import { getSettingsFromDOM } from '../utils/helpers.js';
import { getSettings } from './settings.js';

let onConfirmCallback = null;
let modalPausedRecording = false;

function rebindModalEventListeners(modal) {
    const saveAndPreviewFromModal = async () => {
        const settingsFromModal = getSettingsFromDOM(modal);
        const response = await fetch('/preview_prompt_addition', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settingsFromModal),
        });
        const data = await response.json();
        const modalPreviewContent = modal.querySelector('#prompt-preview-content');
        if (modalPreviewContent) {
            modalPreviewContent.textContent = data.prompt_text || '';
        }

        const modalCountElement = modal.querySelector('#modal-selected-contacts-count');
        if (modalCountElement) {
            const count = settingsFromModal.selected_contacts.length;
            modalCountElement.textContent = count > 0 ? `(${count})` : '';
        }
    };

    modal.querySelectorAll('.settings-group-header, .prompt-preview-container h4').forEach(header => {
        header.addEventListener('click', () => header.parentElement.classList.toggle('collapsed'));
    });

    const elementsToRebind = [
        ...modal.querySelectorAll('#modal-settings-tab input, #modal-settings-tab textarea'),
        ...modal.querySelectorAll('#contacts-content-wrapper input')
    ];
    elementsToRebind.forEach(el => {
        el.addEventListener('input', saveAndPreviewFromModal);
        el.addEventListener('change', saveAndPreviewFromModal);
    });
}

async function saveModalSettings() {
    const settingsFromModal = getSettingsFromDOM(modal);
    await fetch('/save_web_settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settingsFromModal)
    });
}

function hideConfirmationModal() {
    // Не вызываем saveModalSettings() здесь, так как оно уже вызывается
    // в обработчиках кнопок Confirm и Cancel.
    // Просто перезагружаем страницу, чтобы отразить сохраненные изменения.
    if(window.location) window.location.reload();

    modal.style.display = 'none';
    document.body.style.overflow = '';

    if (modalPausedRecording && onConfirmCallback) {
         fetch('/resume');
    }

    onConfirmCallback = null;
    modalPausedRecording = false;
}

export function showConfirmationModal(onConfirm, newTemplateData = null) {
    onConfirmCallback = onConfirm;

    const settingsContent = document.getElementById('settings-tab').cloneNode(true);
    const contactsContent = document.getElementById('contacts-content-wrapper').cloneNode(true);
    const previewContent = document.getElementById('prompt-preview-container').cloneNode(true);

    modalSettingsCol.innerHTML = '<h4>Настройки</h4>';
    modalContactsCol.innerHTML = '<h4>Участники <span id="modal-selected-contacts-count" class="selected-count"></span></h4>';
    modalPreviewCol.innerHTML = '<h4>Предпросмотр</h4>';

    modalSettingsCol.appendChild(settingsContent);
    modalContactsCol.appendChild(contactsContent);
    modalPreviewCol.appendChild(previewContent);

    settingsContent.classList.remove('tab-content');
    settingsContent.id = 'modal-settings-tab';
    contactsContent.id = 'modal-contacts-content-wrapper';
    
    const modalPreviewContainer = previewContent.closest('.prompt-preview-container');
    if (modalPreviewContainer) {
        modalPreviewContainer.classList.remove('collapsed');
    }

    modal.style.display = 'flex';
    document.body.style.overflow = 'hidden';

    rebindModalEventListeners(modal);
}

export function initModal() {
    if (!modal) return;

    modalConfirmBtn.addEventListener('click', async () => {
        await saveModalSettings(); // Сначала сохраняем
        if (onConfirmCallback) onConfirmCallback(); // Затем выполняем действие
        hideConfirmationModal(); // Затем скрываем и перезагружаем
    });

    modalCancelBtn.addEventListener('click', async () => {
        await saveModalSettings(); // Сохраняем изменения даже при отмене
        hideConfirmationModal();
    });

    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            modalCancelBtn.click(); // Эмулируем клик по кнопке отмены, чтобы сохранить
        }
    });
}

export function showRecreateConfirmationModal({ taskType, date, filename }) {
    if (!recreateModal) return;

    const titleEl = recreateModal.querySelector('h2');
    const useCurrentBtn = recreateModal.querySelector('#recreate-use-current-btn');
    const useSavedBtn = recreateModal.querySelector('#recreate-use-saved-btn');
    const cancelBtn = recreateModal.querySelector('#recreate-cancel-btn');

    const taskName = taskType === 'transcription' ? 'транскрипции' : 'протокола';
    titleEl.textContent = `Пересоздание ${taskName}`;

    const hide = () => {
        recreateModal.style.display = 'none';
        // Удаляем обработчики, чтобы избежать утечек памяти
        useCurrentBtn.replaceWith(useCurrentBtn.cloneNode(true));
        useSavedBtn.replaceWith(useSavedBtn.cloneNode(true));
        cancelBtn.replaceWith(cancelBtn.cloneNode(true));
    };

    // Перепривязываем обработчики, так как мы их удаляем
    recreateModal.querySelector('#recreate-use-current-btn').addEventListener('click', async () => {
        const currentSettings = getSettingsFromDOM(document);
        await fetch(`/update_metadata_and_recreate/${taskType}/${date}/${filename}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(currentSettings)
        });
        hide();
    });

    recreateModal.querySelector('#recreate-use-saved-btn').addEventListener('click', async () => {
        await fetch(`/recreate_${taskType}/${date}/${filename}`, {
            method: 'POST'
        });
        hide();
    });

    recreateModal.querySelector('#recreate-cancel-btn').addEventListener('click', hide);

    recreateModal.addEventListener('click', (e) => {
        if (e.target === recreateModal) {
            hide();
        }
    });

    recreateModal.style.display = 'flex';
}
