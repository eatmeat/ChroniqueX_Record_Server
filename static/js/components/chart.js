import { audioChartCanvas } from '../dom.js';
import { getCurrentStatus, getPostProcessingStatus } from './status.js';

let micHistory, sysHistory, recHistory, postProcessingHistory;
const chartHistorySize = 15000; // ~12.5 минут истории при 50 Гц (20ms интервал)
let currentBgR = 244, currentBgG = 247, currentBgB = 249;
const colorChangeFactor = 0.1;
let isRedrawing = false; // Флаг для предотвращения "гонки состояний" при отрисовке

let lastFrameTime = performance.now();
const timePerPixel = 50; // 50ms per pixel (скорость прокрутки как раньше)
let scrollOffset = 0; // Дробное смещение для плавной прокрутки

function setupCanvas(canvas) {
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);
    return ctx;
}

function amplifyLevel(value) {
    return Math.sqrt(value);
}

function redrawMovingChart() {
    if (isRedrawing) return; // Если предыдущий кадр еще рисуется, пропускаем текущий
    isRedrawing = true;

    const now = performance.now();
    const deltaTime = now - lastFrameTime;
    lastFrameTime = now;

    // Увеличиваем смещение на основе прошедшего времени
    // Это делает скорость прокрутки независимой от FPS
    scrollOffset += deltaTime / timePerPixel;

    // Определяем, на сколько целых пикселей/точек данных мы прокрутили.
    const pixelsScrolled = Math.floor(scrollOffset);
    if (pixelsScrolled > 0) {
        // Сдвигаем массивы данных на количество прокрученных пикселей.
        // Если данных не хватает (например, при задержке сети), добавляем 'null', чтобы сохранить синхронизацию.
        for (let i = 0; i < pixelsScrolled; i++) {
            micHistory.shift(); micHistory.push(null);
            sysHistory.shift(); sysHistory.push(null);
            recHistory.shift(); recHistory.push(null);
            postProcessingHistory.shift(); postProcessingHistory.push(null);
        }
        scrollOffset -= pixelsScrolled; // Компенсируем смещение, оставляя только дробную часть.
    }

    const canvas = audioChartCanvas;
    const dpr = window.devicePixelRatio || 1;
    const ctx = canvas.getContext('2d');
    const width = canvas.width / dpr;
    const height = canvas.height / dpr;

    // Определяем, находимся ли мы в PiP-окне
    const isPiP = canvas.ownerDocument !== document && window.documentPictureInPicture?.window;

    const chartHeight = isPiP ? height : height - 40;
    ctx.clearRect(0, 0, width, height);

    const bgGradient = ctx.createLinearGradient(0, 0, 0, chartHeight);
    bgGradient.addColorStop(0, '#ffffff');
    bgGradient.addColorStop(1, '#f7f9fa');
    ctx.fillStyle = bgGradient;
    ctx.fillRect(0, 0, width, chartHeight);

    // Находим последние известные значения для заполнения пустот
    const findLastKnownValue = (history) => {
        for (let i = history.length - 1; i >= 0; i--) {
            if (history[i] !== null && history[i] !== undefined) {
                return history[i];
            }
        }
        return 0;
    };

    // Отрисовка фона для постобработки
    // Добавляем +1 к ширине, чтобы избежать "прыжка" при прокрутке
    const pointsToDrawForBg = Math.ceil(width + 1);
    const postProcessingSlice = postProcessingHistory.slice(postProcessingHistory.length - pointsToDrawForBg);
    const lastPostProcessingValue = findLastKnownValue(postProcessingHistory);
    for (let i = 0; i < postProcessingSlice.length; i++) {
        const value = postProcessingSlice[i] !== null && postProcessingSlice[i] !== undefined 
            ? postProcessingSlice[i] 
            : lastPostProcessingValue;
        if (value !== 0) {
            if (value === 1) { // Транскрибация
                ctx.fillStyle = 'rgba(241, 196, 15, 0.2)'; // Желтый
            } else if (value === 2) { // Протокол
                ctx.fillStyle = 'rgba(46, 204, 113, 0.2)'; // Зеленый
            }
            const x = width - postProcessingSlice.length + i;
            ctx.fillRect(x, 0, 1, chartHeight);
        }
    }

    const recSlice = recHistory.slice(recHistory.length - pointsToDrawForBg);
    const lastRecValue = findLastKnownValue(recHistory);
    ctx.fillStyle = 'rgba(192, 57, 43, 0.2)';
    for (let i = 0; i < recSlice.length; i++) {
        const value = recSlice[i] !== null && recSlice[i] !== undefined 
            ? recSlice[i] 
            : lastRecValue;
        if (value === 1) {
            const x = width - recSlice.length + i;
            ctx.fillRect(x, 0, 1, chartHeight);
        }
    }

    // Сдвигаем всю систему координат влево на величину смещения
    ctx.save();
    ctx.translate(-(scrollOffset % 1), 0);

    const drawWaveBackground = (history, color) => {
        const pointsToDraw = Math.min(history.length, pointsToDrawForBg);
        const historySlice = history.slice(history.length - pointsToDraw);

        // Находим первое известное значение для старта от левого края
        let firstKnownValue = 0;
        let firstPointIndex = -1;
        for (let i = 0; i < historySlice.length; i++) {
            if (historySlice[i] !== null && historySlice[i] !== undefined) {
                firstKnownValue = historySlice[i];
                firstPointIndex = i;
                break;
            }
        }

        if (firstPointIndex === -1) return; // Нет данных для отрисовки

        // Находим последнее известное значение для завершения у правого края
        let lastKnownValue = firstKnownValue;
        for (let i = historySlice.length - 1; i >= firstPointIndex; i--) {
            if (historySlice[i] !== null && historySlice[i] !== undefined) {
                lastKnownValue = historySlice[i];
                break;
            }
        }

        ctx.beginPath();
        ctx.moveTo(0, chartHeight); // Начинаем с левого нижнего угла

        // Начинаем линию от левого края с первым известным значением
        const startY = chartHeight - Math.min(1, firstKnownValue) * chartHeight;
        ctx.lineTo(0, startY);

        for (let i = firstPointIndex; i < historySlice.length; i++) {
            const value = historySlice[i];
            if (value !== null && value !== undefined) {
                const x = width - pointsToDraw + i + 1;
                const y = chartHeight - Math.min(1, value) * chartHeight;
                ctx.lineTo(x, y);
            }
        }

        // Завершаем линию до правого края с последним известным значением
        const endY = chartHeight - Math.min(1, lastKnownValue) * chartHeight;
        ctx.lineTo(width, endY);

        ctx.lineTo(width, chartHeight); // Правый нижний угол
        ctx.closePath();

        ctx.fillStyle = color;
        ctx.fill();
    };
    drawWaveBackground(sysHistory, 'rgba(52, 152, 219, 0.08)');
    drawWaveBackground(micHistory, 'rgba(231, 76, 60, 0.08)');

    ctx.strokeStyle = '#aaaaaa';
    ctx.lineWidth = 0.5;
    for (let i = 1; i < 4; i++) {
        const y = chartHeight * (i / 4);
        ctx.beginPath();
        ctx.moveTo(0, y); ctx.lineTo(width, y);
        ctx.stroke();
    }

    const dateNow = new Date();
    const endTime = dateNow.getTime() - (scrollOffset * timePerPixel);
    const startTime = endTime - width * timePerPixel;
    const seconds = dateNow.getSeconds();
    const secondsUntilNextMark = seconds < 30 ? 30 - seconds : 60 - seconds;

    // Определяем вертикальное положение для текста времени
    const timeY1 = isPiP ? 20 : height - 22;
    const timeY2 = isPiP ? 38 : height - 2;
    const timeFontSize = isPiP ? 16 : 18;

    if (secondsUntilNextMark <= 20 && secondsUntilNextMark > 0) {
        const mskTime = dateNow.toLocaleTimeString('ru-RU', { timeZone: 'Europe/Moscow', hour: '2-digit', minute: '2-digit', second: '2-digit' });
        const irkTime = dateNow.toLocaleTimeString('ru-RU', { timeZone: 'Asia/Irkutsk', hour: '2-digit', minute: '2-digit', second: '2-digit' });

        ctx.textAlign = 'right';
        // В PiP-окне делаем текст более контрастным для лучшей читаемости
        ctx.fillStyle = isPiP ? 'rgba(0, 0, 0, 0.6)' : 'rgba(127, 140, 141, 0.5)';
        ctx.font = `500 ${timeFontSize}px Ubuntu, sans-serif`;
        if (isPiP) ctx.shadowColor = 'white';
        if (isPiP) ctx.shadowBlur = 5;
        ctx.fillText(`МСК: ${mskTime}`, width - 5 + (scrollOffset % 1), timeY1);
        ctx.fillText(`ИРК: ${irkTime}`, width - 5 + (scrollOffset % 1), timeY2);
    }

    let lastMarkTime = new Date(endTime);
    lastMarkTime.setMilliseconds(0);
    lastMarkTime.setSeconds(Math.floor(lastMarkTime.getSeconds() / 5) * 5);

    while (lastMarkTime.getTime() >= startTime) {
        const timeDiff = endTime - lastMarkTime.getTime();
        const x = width - (timeDiff / timePerPixel);
        const markSeconds = lastMarkTime.getSeconds();

        if (markSeconds === 0 || markSeconds === 30) {
            ctx.strokeStyle = '#aaaaaa';
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(x, 0); ctx.lineTo(x, chartHeight);
            ctx.stroke();
            const mskTime = lastMarkTime.toLocaleTimeString('ru-RU', { timeZone: 'Europe/Moscow', hour: '2-digit', minute: '2-digit', second: '2-digit' });
            const irkTime = lastMarkTime.toLocaleTimeString('ru-RU', { timeZone: 'Asia/Irkutsk', hour: '2-digit', minute: '2-digit', second: '2-digit' });
            
            ctx.fillStyle = '#7f8c8d';
            ctx.font = `500 ${timeFontSize}px Ubuntu, sans-serif`;
            ctx.textAlign = 'right';
            if (isPiP) ctx.shadowColor = 'white';
            if (isPiP) ctx.shadowBlur = 5;
            ctx.fillText(`МСК: ${mskTime}`, x - 5, timeY1);
            ctx.fillText(`ИРК: ${irkTime}`, x - 5, timeY2);
        }
        else {
            ctx.strokeStyle = '#aaaaaa';
            ctx.lineWidth = 0.5;
            ctx.beginPath();
            ctx.moveTo(x, 0); ctx.lineTo(x, chartHeight);
            ctx.stroke();
        }

        // Сбрасываем тень после отрисовки текста
        if (isPiP) ctx.shadowBlur = 0;

        lastMarkTime.setSeconds(lastMarkTime.getSeconds() - 5);
    }

    ctx.lineWidth = 1.5;

    // Оптимизированная функция отрисовки линии
    const drawLine = (history, color) => {
        const pointsToDraw = Math.min(history.length, pointsToDrawForBg);
        const historySlice = history.slice(history.length - pointsToDraw);

        ctx.beginPath();
        ctx.strokeStyle = color;

        // Находим первое известное значение для старта линии от левого края
        let firstKnownValue = 0;
        let firstPointIndex = -1;
        for (let i = 0; i < historySlice.length; i++) {
            if (historySlice[i] !== null && historySlice[i] !== undefined) {
                firstKnownValue = historySlice[i];
                firstPointIndex = i;
                break;
            }
        }

        if (firstPointIndex === -1) return; // Нет данных для отрисовки

        // Находим последнее известное значение для завершения линии у правого края
        let lastKnownValue = firstKnownValue;
        for (let i = historySlice.length - 1; i >= firstPointIndex; i--) {
            if (historySlice[i] !== null && historySlice[i] !== undefined) {
                lastKnownValue = historySlice[i];
                break;
            }
        }

        // Начинаем линию от левого края графика (x=0) с первым известным значением
        const startY = chartHeight - Math.min(1, firstKnownValue) * chartHeight;
        ctx.moveTo(0, startY);

        // Рисуем линию от первой найденной точки до конца
        for (let i = firstPointIndex; i < historySlice.length; i++) {
            const value = historySlice[i];
            if (value !== null && value !== undefined) { // Рисуем линию только если есть данные
                const x = width - pointsToDraw + i + 1;
                const y = chartHeight - Math.min(1, value) * chartHeight;
                ctx.lineTo(x, y);
            }
        }

        // Завершаем линию до правого края графика (x=width) с последним известным значением
        const endY = chartHeight - Math.min(1, lastKnownValue) * chartHeight;
        ctx.lineTo(width, endY);

        ctx.stroke();
    };

    // Оптимизированная функция для линии с изменяемым цветом (группировка по цвету)
    const drawMultiColorLine = (history, colorFunc) => {
        const pointsToDraw = Math.min(history.length, pointsToDrawForBg);
        const historySlice = history.slice(history.length - pointsToDraw);

        // Находим первое известное значение для старта линии от левого края
        let firstKnownValue = 0;
        let firstPointIndex = -1;
        for (let i = 0; i < historySlice.length; i++) {
            if (historySlice[i] !== null && historySlice[i] !== undefined) {
                firstKnownValue = historySlice[i];
                firstPointIndex = i;
                break;
            }
        }

        if (firstPointIndex === -1) return; // Нет данных для отрисовки

        // Находим последнее известное значение для завершения линии у правого края
        let lastKnownValue = firstKnownValue;
        for (let i = historySlice.length - 1; i >= firstPointIndex; i--) {
            if (historySlice[i] !== null && historySlice[i] !== undefined) {
                lastKnownValue = historySlice[i];
                break;
            }
        }

        let lastColor = colorFunc(firstKnownValue);
        let pathStarted = false;

        // Начинаем линию от левого края графика (x=0) с первым известным значением
        const startY = chartHeight - Math.min(1, firstKnownValue) * chartHeight;
        ctx.beginPath();
        ctx.strokeStyle = lastColor;
        ctx.moveTo(0, startY);
        pathStarted = true;

        for (let i = firstPointIndex; i < historySlice.length; i++) {
            const value = historySlice[i];
            if (value === null || value === undefined) continue; // Пропускаем пустые значения

            const color = colorFunc(value);

            if (color !== lastColor) {
                // Если цвет изменился, завершаем старый путь и начинаем новый
                ctx.stroke();
                ctx.beginPath();
                ctx.strokeStyle = color;
                lastColor = color;
            }

            // Продолжаем рисовать линию
            const x = width - pointsToDraw + i + 1;
            const y = chartHeight - Math.min(1, value) * chartHeight;
            ctx.lineTo(x, y);
        }

        // Завершаем линию до правого края графика (x=width) с последним известным значением
        const endY = chartHeight - Math.min(1, lastKnownValue) * chartHeight;
        ctx.lineTo(width, endY);

        if (pathStarted) {
            ctx.stroke(); // Завершаем последний начатый путь
        }
    };

    drawLine(sysHistory, '#3498db'); // Используем быструю отрисовку для системного звука
    drawMultiColorLine(micHistory, value => value > 0.9 ? '#ff0000' : (value > 0.7 ? '#e74c3c' : '#c0392b'));

    ctx.restore(); // Возвращаем систему координат в исходное состояние

    isRedrawing = false; // Завершили отрисовку
}

const dataFetchInterval = 10; // Интервал получения данных в мс (50 Гц)

function renderLoop() {
    redrawMovingChart();
    requestAnimationFrame(renderLoop); // Планируем следующий кадр
}

async function updateAudioLevels() {
    try {
        const response = await fetch('/audio_levels');
        if (response.status === 401) {
            window.location.href = '/login';
            return;
        }
        const levels = await response.json();
    
        const amplifiedMic = amplifyLevel(levels.mic < 0 ? 0 : levels.mic);
        const amplifiedSys = amplifyLevel(levels.sys < 0 ? 0 : levels.sys);
    
        // Определяем значение для истории записи
        const recValue = (getCurrentStatus() === 'rec') ? 1 : 0;
    
        // Определяем значение для истории постобработки
        const postProcessingStatus = getPostProcessingStatus();
        let postProcessingValue = 0; // 0 - нет, 1 - транскрибация, 2 - протокол
        if (postProcessingStatus.active) {
            if (postProcessingStatus.info.toLowerCase().includes('транскрибация')) postProcessingValue = 1;
            else if (postProcessingStatus.info.toLowerCase().includes('протокол')) postProcessingValue = 2;
        }
    
        // Обновляем историю. Для фонов (запись, постобработка) мы заполняем все 'null'
        // с момента последнего обновления, чтобы фон был сплошным.
        for (let i = recHistory.length - 1; i >= 0; i--) {
            if (recHistory[i] === null) {
                // Заполняем все пропуски для фонов
                recHistory[i] = recValue;
                postProcessingHistory[i] = postProcessingValue;
            } else {
                break; // Останавливаемся, как только дошли до уже заполненных данных
            }
        }

        // Для уровней звука мы заменяем только последний 'null', чтобы показать "живой" уровень,
        // а не создавать "полки" на графике.
        micHistory[micHistory.length - 1] = amplifiedMic;
        sysHistory[sysHistory.length - 1] = amplifiedSys;

    } catch (error) {
        // console.error('Error fetching audio levels:', error);
    } finally {
        // Рекурсивно планируем следующее обновление, чтобы избежать наложения запросов
        setTimeout(updateAudioLevels, dataFetchInterval);
    }
}

export function initChart() {
    if (!audioChartCanvas) return;
    
    micHistory = new Array(chartHistorySize).fill(null);
    sysHistory = new Array(chartHistorySize).fill(null);
    recHistory = new Array(chartHistorySize).fill(null);
    postProcessingHistory = new Array(chartHistorySize).fill(null);

    let currentCanvasWidth = 0;
    let currentCanvasHeight = 0;

    const initialCtx = setupCanvas(audioChartCanvas);
    currentCanvasWidth = audioChartCanvas.getBoundingClientRect().width;
    currentCanvasHeight = audioChartCanvas.getBoundingClientRect().height;

    window.addEventListener('resize', () => {
        const rect = audioChartCanvas.getBoundingClientRect();
        if (rect.width !== currentCanvasWidth || rect.height !== currentCanvasHeight) {
            setupCanvas(audioChartCanvas);
            currentCanvasWidth = rect.width;
            currentCanvasHeight = rect.height;
        }
    });

    updateAudioLevels(); // Запускаем первый вызов для получения данных
    renderLoop(); // Запускаем цикл отрисовки
}

export { setupCanvas };
