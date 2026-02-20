import {
    statusIndicator,
    statusText,
    statusTime,
    postProcessStatus,
    recBtn,
    pauseBtn,
    stopBtn,
    favicon,
    volumeMetersContainer
} from '../dom.js';

let currentStatus = 'stop';

export async function updateStatus() {
    try {
        const response = await fetch('/status');
        if (!response.ok) {
            if (response.status === 401) {
                window.location.href = '/login';
            }
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();

        currentStatus = data.status;
        statusTime.textContent = `(${data.time})`;

        // Update status indicator and text
        statusIndicator.className = 'status-indicator ' + data.status;
        switch (data.status) {
            case 'rec':
                statusText.textContent = 'Запись';                    
                recBtn.textContent = 'REC'; // Убедимся, что текст кнопки правильный
                if (volumeMetersContainer) volumeMetersContainer.classList.add('recording');
                break;
            case 'paused':
                statusText.textContent = 'Пауза';
                recBtn.textContent = 'RESUME'; // Меняем текст кнопки на "RESUME" в режиме паузы
                if (volumeMetersContainer) volumeMetersContainer.classList.remove('recording');
                break;
            case 'stop':
            default:
                statusText.textContent = 'Остановлено';
                recBtn.textContent = 'REC'; // Возвращаем исходный текст
                if (volumeMetersContainer) volumeMetersContainer.classList.remove('recording');
                break;
        }

        // Update control buttons state
        recBtn.disabled = data.status === 'rec';
        pauseBtn.disabled = data.status !== 'rec';
        stopBtn.disabled = data.status === 'stop';
        
        // Update favicon
        if(favicon) favicon.href = `/favicon.ico?v=${new Date().getTime()}`;

        // Update post-processing status
        if (postProcessStatus) {
            if (data.post_processing.active) {
                postProcessStatus.textContent = data.post_processing.info; // Показываем текст
            } else {
                postProcessStatus.innerHTML = '&nbsp;'; // Вставляем неразрывный пробел для сохранения высоты
            }
        }

    } catch (error) {
        console.error('Error fetching status:', error);
        if(statusText) statusText.textContent = 'Ошибка соединения';
        if(statusIndicator) statusIndicator.className = 'status-indicator stop';
    }
}

export function getCurrentStatus() {
    return currentStatus;
}
