import { pipBtn, audioChartCanvas, volumeMetersContainer } from '../dom.js';
import { setupCanvas } from './chart.js';

let pipWindow = null;
let chartPlaceholder = null;
let controlsPlaceholder = null;

async function togglePiP() {
    if (!('documentPictureInPicture' in window)) {
        alert('Ваш браузер не поддерживает режим "Картинка в картинке" для HTML-элементов.');
        return;
    }

    if (pipWindow) {
        pipWindow.close();
        return;
    }

    try {
        pipWindow = await window.documentPictureInPicture.requestWindow({
            width: audioChartCanvas.width / (window.devicePixelRatio || 1),
            height: audioChartCanvas.height / (window.devicePixelRatio || 1),
        });

        const pipDocument = pipWindow.document;
        const pipBody = pipDocument.body;
        pipDocument.title = "ChroniqueX Record Server";
 
        // Копируем все теги <link> и <style> из основного документа в PiP окно
        // Это более надежный способ, который избегает ошибок с CORS
        document.head.querySelectorAll('link[rel="stylesheet"], style').forEach(node => pipDocument.head.appendChild(node.cloneNode(true)));

        const controlsContainer = document.querySelector('.controls');
        const volumeChart = document.querySelector('.volume-chart');
        const statusWrapper = document.querySelector('.status-wrapper');

        if (controlsContainer) {
            const computedStyle = window.getComputedStyle(controlsContainer);
            controlsPlaceholder = document.createElement('div');
            controlsPlaceholder.id = 'controls-placeholder';
            controlsPlaceholder.style.height = `${controlsContainer.offsetHeight}px`;
            controlsPlaceholder.style.marginTop = computedStyle.marginTop;
            controlsPlaceholder.style.marginBottom = computedStyle.marginBottom;
            controlsPlaceholder.style.marginLeft = computedStyle.marginLeft;
            controlsPlaceholder.style.marginRight = computedStyle.marginRight;
            controlsContainer.parentNode.insertBefore(controlsPlaceholder, controlsContainer);
        }

        const legendEl = volumeMetersContainer.querySelector('.chart-legend');
        if (legendEl) legendEl.style.display = 'none';

        if (volumeMetersContainer) {
            chartPlaceholder = document.createElement('div');
            chartPlaceholder.id = 'pip-placeholder';
            chartPlaceholder.style.cssText = `
                display: flex;
                flex-direction: column;
                justify-content: center;
                align-items: center;
                height: ${volumeMetersContainer.offsetHeight + 21}px;
                box-sizing: border-box;
                padding: 20px;
                text-align: center;
                font-size: 1.2em;
                color: #7f8c8d;
            `;
            chartPlaceholder.innerHTML = `
                <p>Режим «картинка в картинке» активен</p>
                <button class="control-btn pip-btn">Вернуть</button>
            `;
            volumeMetersContainer.parentNode.replaceChild(chartPlaceholder, volumeMetersContainer);
            chartPlaceholder.querySelector('button').addEventListener('click', () => pipWindow.close());
        }

        pipBody.style.display = 'flex';
        pipBody.style.flexDirection = 'column';
        pipBody.style.padding = '0';
        pipBody.style.overflow = 'hidden';
        pipBody.style.margin = '0';
        if (statusWrapper) statusWrapper.style.alignItems = 'center';
        if (statusWrapper) statusWrapper.style.display = 'none';
        if (volumeChart) volumeChart.style.margin = '0';
        if (volumeChart) volumeChart.style.width = '100%';
        controlsContainer.style.padding = '10px 0';
        const pipStatusWrapper = statusWrapper ? statusWrapper.cloneNode(true) : null;
        if (pipStatusWrapper) pipStatusWrapper.style.display = 'flex';
        if (pipStatusWrapper) pipStatusWrapper.style.padding = '0 10px';
        controlsContainer.style.margin = '0';
        if (pipStatusWrapper) pipBody.append(pipStatusWrapper);
        if (volumeChart) pipBody.append(volumeChart);
        pipBody.append(controlsContainer);
        pipBtn.classList.add('active');
        
        const adjustPiPLayout = (win) => {
            const pipDoc = win.document;
            if (!pipDoc) return;
        
            const controlsEl = pipDoc.querySelector('.controls');
            const statusEl = pipDoc.querySelector('.status-wrapper');
            const canvasEl = pipDoc.getElementById('audio-chart');
        
            if (!controlsEl || !canvasEl) return;
        
            const controlsHeight = controlsEl.offsetHeight;
            const statusHeight = statusEl ? statusEl.offsetHeight : 0;
            const controlsPadding = 0;
            const canvasBorder = 2;
            
            const totalNonCanvasHeight = controlsHeight + statusHeight + canvasBorder + controlsPadding;
            const availableHeight = pipDoc.documentElement.clientHeight - totalNonCanvasHeight;
        
            canvasEl.style.height = `${Math.max(20, availableHeight)}px`;
            setupCanvas(canvasEl);
        };

        // Запускаем интервал для корректировки макета в течение первой секунды.
        // Это надежно решает проблему "сжатого" вида при повторном открытии окна.
        let adjustInterval = pipWindow.setInterval(() => {
            adjustPiPLayout(pipWindow);
        }, 50); // Корректируем каждые 50 мс

        // Через 50 мс отключаем интервал, так как окно уже должно было стабилизироваться.
        pipWindow.setTimeout(() => {
            pipWindow.clearInterval(adjustInterval);
        }, 50);

        pipWindow.addEventListener('resize', () => adjustPiPLayout(pipWindow));
        pipWindow.addEventListener('pagehide', () => {
            // Сбрасываем стили, которые были применены к элементам в PiP-окне,
            // чтобы при следующем открытии они не влияли на расчеты.
            if (statusWrapper) statusWrapper.style.display = '';
            controlsContainer.style.margin = '';
            
            if (legendEl) legendEl.style.display = '';
            if (chartPlaceholder && chartPlaceholder.parentNode) {
                chartPlaceholder.parentNode.replaceChild(volumeMetersContainer, chartPlaceholder);
            }
            chartPlaceholder = null;
            if (statusWrapper) statusWrapper.style.alignItems = '';
            if (volumeMetersContainer && volumeChart) {
                volumeMetersContainer.prepend(volumeChart);
            }
            if (volumeChart) volumeChart.style.margin = '';
            if (volumeChart) volumeChart.style.width = '';
            const canvasEl = volumeMetersContainer.querySelector('#audio-chart');
            if (canvasEl) canvasEl.style.height = '';
            setupCanvas(audioChartCanvas);
            controlsContainer.style.padding = '';
            const mainControlsExtensions = document.querySelector('.main-controls-extensions');
            if (mainControlsExtensions) mainControlsExtensions.insertAdjacentElement('beforebegin', controlsContainer);
            if (controlsPlaceholder && controlsPlaceholder.parentNode) {
                controlsPlaceholder.parentNode.replaceChild(controlsContainer, controlsPlaceholder);
            }
            controlsPlaceholder = null;

            pipBtn.classList.remove('active');
            pipWindow = null;
        });

    } catch (error) { console.error('Ошибка при открытии PiP окна:', error); }
}


export function initPiP() {
    if (!pipBtn) return;

    if (!('documentPictureInPicture' in window)) {
        pipBtn.style.display = 'none';
    } else {
        pipBtn.addEventListener('click', togglePiP);
    }
}
