import { recBtn, pauseBtn, stopBtn, addFileBtn, fileUploadInput } from './dom.js';
import { initTabs } from './components/tabs.js';
import { updateStatus, getCurrentStatus } from './components/status.js';
import { initChart } from './components/chart.js';
import { initPiP } from './components/pip.js';
import { initRecordingsList } from './components/recordingsList.js';
import { initSettings } from './components/settings.js';
import { initContacts } from './components/contacts.js';
import { initModal, showConfirmationModal } from './components/modal.js';

document.addEventListener('DOMContentLoaded', function () {
    // Initialize all modules
    initTabs();
    initChart();
    initPiP();
    initRecordingsList();
    initSettings();
    initContacts();
    initModal();

    // Initial status update
    updateStatus();
    setInterval(updateStatus, 1000);

    // Control button event listeners
    recBtn?.addEventListener('click', () => {
        if (getCurrentStatus() === 'paused') {
            fetch('/resume');
        } else {
            fetch('/rec');
        }
    });
    pauseBtn?.addEventListener('click', () => fetch('/pause'));
    stopBtn?.addEventListener('click', async () => {
        const response = await fetch('/get_web_settings');
        const settings = await response.json();
        if (settings.confirm_prompt_on_action) {
            // Показываем модальное окно. При подтверждении, настройки из окна
            // будут переданы в этот колбэк.
            showConfirmationModal((settingsFromModal) => {
                // Отправляем настройки на сервер вместе с командой stop
                fetch('/stop', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(settingsFromModal) });
            });
        } else {
            fetch('/stop', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(settings) });
        }
    });

    addFileBtn?.addEventListener('click', () => {
        fileUploadInput.click();
    });

    fileUploadInput?.addEventListener('change', async (event) => {
        const file = event.target.files[0];
        if (!file) return;

        const uploadFile = (settings) => {
            const formData = new FormData();
            formData.append('file', file);
            formData.append('settings', JSON.stringify(settings));

            fetch('/add_file', { method: 'POST', body: formData })
                .then(res => {
                    // Проверяем, не вернул ли сервер ошибку (например, 500)
                    if (!res.ok) {
                        // Если есть ошибка, пытаемся извлечь сообщение и пробросить его дальше
                        return res.json().then(errData => { throw new Error(errData.message || 'Ошибка сервера'); });
                    }
                    return res.json();
                })
                .then(data => {
                    // Показываем alert, только если в ответе от сервера есть статус "error"
                    if (data.status === 'error') {
                        alert(data.message || 'Произошла ошибка при обработке файла.');
                    }
                    // Если статус "ok", ничего не делаем.
                })
                .catch(err => alert(`Ошибка загрузки: ${err.message || err}`));
        };

        const response = await fetch('/get_web_settings');
        const settings = await response.json();
        if (settings.confirm_prompt_on_action) {
            showConfirmationModal(uploadFile);
        } else {
            uploadFile(settings);
        }
        event.target.value = ''; // Сбрасываем значение, чтобы можно было выбрать тот же файл снова
    });

    // Global fetch error handler
    document.addEventListener('fetch-error', function(e) {
        if (e.detail.status === 401) { 
            window.location.href = '/login'; 
        }
    });
});
