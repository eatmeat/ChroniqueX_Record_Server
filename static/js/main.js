import { recBtn, pauseBtn, stopBtn } from './dom.js';
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
            fetch('/stop');
        }
    });

    // Global fetch error handler
    document.addEventListener('fetch-error', function(e) {
        if (e.detail.status === 401) { 
            window.location.href = '/login'; 
        }
    });
});
