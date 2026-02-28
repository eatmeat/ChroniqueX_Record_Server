import { modal, modalTitle, modalConfirmBtn, modalCancelBtn, modalSettingsCol, modalContactsCol, modalPreviewCol } from '../dom.js';
import { getSettingsFromDOM } from '../utils/helpers.js';
import { initSettings, loadSettings, toggleMeetingDateSourceVisibility, updatePromptPreview } from './settings.js';
import { initContacts, loadContactsAndSettings, updateSelectedContactsCount } from './contacts.js';

let onConfirmCallback = null;
let modalPausedRecording = false;

async function hideConfirmationModal() {
    modal.style.display = 'none';
    document.body.style.overflow = '';

    // После закрытия модального окна, перезагружаем глобальные настройки на основной странице,
    // чтобы сбросить любые случайные изменения, которые могли быть сделаны в DOM, но не сохранены.
    await loadSettings(); // Сбрасывает настройки
    initContacts(); // Переинициализируем обработчики контактов на основной странице
    
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
        // Добавляем дату в запрос для корректного предпросмотра
        if (isRecreateAction && recordingInfo && recordingInfo.date) {
            // Для пересоздания используем дату конкретной записи
            requestBody.recording_date = recordingInfo.date;
        } else if (!isRecreateAction) {
            // Для новой записи используем текущую дату (важно для предпросмотра "даты из папки")
            requestBody.recording_date = new Date().toISOString().split('T')[0];
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

    // Перед клонированием "отвязываем" обработчики событий от оригинальных элементов,
    // чтобы они не дублировались и не переносились в модальное окно.
    const contactsContainer = document.getElementById('contacts-list-container');
    if (contactsContainer && contactsContainer._mainHandler) {
        contactsContainer.removeEventListener('change', contactsContainer._mainHandler);
        delete contactsContainer._mainHandler; // Удаляем свойство, чтобы избежать утечек
    }

    // Аналогично "отвязываем" обработчики от кнопок добавления в настройках,
    // чтобы избежать их дублирования и срабатывания на основной странице из модального окна.
    const addTemplateBtn = document.getElementById('add-meeting-name-template-btn');
    if (addTemplateBtn && addTemplateBtn._handler) {
        addTemplateBtn.removeEventListener('click', addTemplateBtn._handler);
        delete addTemplateBtn._handler;
    }

    const addRuleBtn = document.getElementById('add-context-rule-btn');
    if (addRuleBtn && addRuleBtn._handler) {
        addRuleBtn.removeEventListener('click', addRuleBtn._handler);
        delete addRuleBtn._handler;
    }

    const settingsContent = document.getElementById('settings-tab').cloneNode(true);
    const contactsContent = document.getElementById('contacts-content-wrapper').cloneNode(true);
    const previewContent = document.getElementById('prompt-preview-container').cloneNode(true);

    modalSettingsCol.innerHTML = '<h4>Настройки</h4>';
    modalContactsCol.innerHTML = '<h4>Голоса <span id="modal-selected-contacts-count" class="selected-count"></span></h4>';
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

    // Убираем группу "Поведение" из модального окна
    const behaviorGroup = modal.querySelector('.behavior-settings-group');
    if (behaviorGroup) {
        behaviorGroup.style.display = 'none';
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

        // Создаем специальный колбэк для контактов, который будет обновлять и предпросмотр, и счетчик
        const contactsUpdateCallback = () => {
            updatePromptPreview(modal);
            updateSelectedContactsCount(modal);
        };
        initContacts(modal, contactsUpdateCallback, settingsToLoad);

        // Если это пересоздание, нужно явно применить настройки к DOM
        // или если это остановка, то загружаем глобальные настройки
        if (isRecreateAction && settingsToLoad) {
            await loadSettings(settingsToLoad, modal);
        } else if (!isRecreateAction) {
            await loadSettings(null, modal); // Загружаем глобальные настройки в модальное окно
        }
        
        // Принудительно обновляем счетчик при каждом открытии
        updateSelectedContactsCount(modal);

        // Вызываем предпросмотр после инициализации всех настроек
        await saveAndPreviewFromModal();
    };

    initializeComponents();
}

export function initModal() {
    if (!modal) return;

    // --- Инициализация обработчиков событий модального окна (выполняется один раз) ---
    
    // Этот обработчик будет вызывать обновление предпросмотра при любом изменении
    const saveAndPreviewFromModal = async () => {
        const settingsFromModal = getSettingsFromDOM(modal);
        const response = await fetch('/preview_prompt_addition', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ...settingsFromModal }),
        });
        const data = await response.json();
        const modalPreviewContent = modal.querySelector('#prompt-preview-content');
        if (modalPreviewContent) {
            modalPreviewContent.textContent = data.prompt_text || '';
        }
        updateSelectedContactsCount(modal);
    };

    // Делегирование для кликов (сворачивание/разворачивание)
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
        if (e.target.matches('input[type="radio"], input[type="checkbox"]')) saveAndPreviewFromModal();
    });
    // --- Конец инициализации обработчиков ---

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
