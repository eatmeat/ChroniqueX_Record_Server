import { modal, modalTitle, modalConfirmBtn, modalCancelBtn, modalSettingsCol, modalContactsCol, modalPreviewCol } from '../dom.js';
import { getSettingsFromDOM } from '../utils/helpers.js';
import { initSettings, loadSettings, updatePromptPreview } from './settings.js';
import { initContacts, loadContactsAndSettings, updateSelectedContactsCount } from './contacts.js';

let onConfirmCallback = null;
let modalPausedRecording = false;

function rebindModalEventListeners(modal, saveAndPreviewFromModal) {
    // Используем делегирование событий, чтобы обработчики работали для динамически добавленных элементов
    // Этот обработчик ТОЛЬКО для групп настроек и предпросмотра. Группы контактов имеют свою логику.
    modal.addEventListener('click', (e) => {
        const settingsHeader = e.target.closest('.settings-group-header');
        const previewHeader = e.target.closest('#modal-preview-col h4');
        if (settingsHeader) {
            settingsHeader.closest('.settings-group')?.classList.toggle('collapsed');
        } else if (previewHeader) {
            previewHeader.parentElement.classList.toggle('collapsed');
        }
    });

    // Делегирование для всех input/change событий в модальном окне
    modal.addEventListener('input', (e) => {
        if (e.target.matches('input, textarea')) saveAndPreviewFromModal();
    });
    modal.addEventListener('change', (e) => {
        if (e.target.matches('input')) saveAndPreviewFromModal();
    });
}

async function hideConfirmationModal() {
    modal.style.display = 'none';
    document.body.style.overflow = '';

    // После закрытия модального окна, перезагружаем глобальные настройки на основной странице,
    // чтобы сбросить любые случайные изменения, которые могли быть сделаны в DOM, но не сохранены.
    loadSettings();

    onConfirmCallback = null;
    modalPausedRecording = false;
}

export function showConfirmationModal(onConfirm, recordingInfo = null) {
    onConfirmCallback = onConfirm;
    // Если нет recordingInfo, значит это остановка записи, а не пересоздание.
    const isRecreateAction = recordingInfo && recordingInfo.date && recordingInfo.filename;

    if (modalTitle) {
        modalTitle.textContent = isRecreateAction
            ? 'Подтверждение настроек для пересоздания'
            : 'Подтверждение настроек для новой записи';
    }

    const saveAndPreviewFromModal = async () => {
        const settingsFromModal = getSettingsFromDOM(modal);
        const requestBody = {
            ...settingsFromModal
        };
        // Если это пересоздание, добавляем дату записи в запрос для корректного предпросмотра
        if (isRecreateAction && recordingInfo && recordingInfo.date) {
            requestBody.recording_date = recordingInfo.date;
        }
        const response = await fetch('/preview_prompt_addition', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestBody),
        });
        const data = await response.json();
        const modalPreviewContent = modal.querySelector('#prompt-preview-content');
        if (modalPreviewContent) {
            modalPreviewContent.textContent = data.prompt_text || '';
        }

        updateSelectedContactsCount(modal);
    };

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

    rebindModalEventListeners(modal, saveAndPreviewFromModal);
    
    // Убираем группу "Поведение" из модального окна
    const behaviorGroup = modal.querySelector('.behavior-settings-group');
    if (behaviorGroup) {
        behaviorGroup.remove();
    }

    const initializeComponents = async () => {
        let settingsToLoad = null;
        if (isRecreateAction) {
            // Загружаем настройки из метаданных конкретной записи
            const { date, filename } = recordingInfo;
            const response = await fetch(`/get_metadata/${date}/${filename}`);
            const metadata = await response.json();
            settingsToLoad = metadata.settings || {}; // Используем настройки из метаданных
        }

        // Переинициализируем логику компонентов внутри модального окна
        // Передаем загруженные настройки, если они есть
        initSettings(modal, saveAndPreviewFromModal, settingsToLoad);
        initContacts(modal, saveAndPreviewFromModal, settingsToLoad);

        // Если это пересоздание, нужно явно применить настройки к DOM
        // или если это остановка, то загружаем глобальные настройки
        if (isRecreateAction && settingsToLoad) {
            await loadSettings(settingsToLoad, modal);
        } else if (!isRecreateAction) {
            await loadSettings(null, modal); // Загружаем глобальные настройки в модальное окно
        }
    };

    initializeComponents();
}

export function initModal() {
    if (!modal) return;

    modalConfirmBtn.addEventListener('click', async () => {
        if (onConfirmCallback) {
            // Для любого действия (стоп или пересоздание) передаем настройки из модального окна в колбэк.
            // Колбэк сам решит, что с ними делать.
            const settingsFromModal = getSettingsFromDOM(modal);
            onConfirmCallback(settingsFromModal);
        }
        hideConfirmationModal();
    });

    modalCancelBtn.addEventListener('click', () => {
        hideConfirmationModal();
    });

    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            modalCancelBtn.click(); // Эмулируем клик по кнопке отмены, чтобы сохранить
        }
    });
}
