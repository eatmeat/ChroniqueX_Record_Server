import { audioChartCanvas } from '../dom.js';
import { getCurrentStatus, getPostProcessingStatus } from './status.js';

let micHistory, sysHistory, recHistory, postProcessingHistory;
const chartHistorySize = 6000; // ~5 минут истории при 20 fps (50ms интервал)
let frameCount = 0;
const scrollInterval = 1;
let currentBgR = 244, currentBgG = 247, currentBgB = 249;
const colorChangeFactor = 0.1;

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
    const canvas = audioChartCanvas;
    const dpr = window.devicePixelRatio || 1;
    const ctx = canvas.getContext('2d');

    const width = canvas.width / dpr;
    const height = canvas.height / dpr;
    const chartHeight = height - 40;

    ctx.clearRect(0, 0, width, height);

    const currentMicLevel = micHistory[micHistory.length - 1] || 0;
    const currentSysLevel = sysHistory[sysHistory.length - 1] || 0;

    const micEffect = Math.min(1, currentMicLevel * 2.5);
    const sysEffect = Math.min(1, currentSysLevel * 2.5);

    let targetR = 244, targetG = 247, targetB = 249;
    targetR = targetR * (1 - micEffect) + 255 * micEffect;
    targetG = targetG * (1 - micEffect) + 210 * micEffect;
    targetB = targetB * (1 - micEffect) + 210 * micEffect;
    targetR = targetR * (1 - sysEffect) + 210 * sysEffect;
    targetG = targetG * (1 - sysEffect) + 225 * sysEffect;
    targetB = targetB * (1 - sysEffect) + 255 * sysEffect;

    currentBgR += (targetR - currentBgR) * colorChangeFactor;
    currentBgG += (targetG - currentBgG) * colorChangeFactor;
    currentBgB += (targetB - currentBgB) * colorChangeFactor;
    document.body.style.backgroundColor = `rgb(${Math.round(currentBgR)},${Math.round(currentBgG)},${Math.round(currentBgB)})`;

    const bgGradient = ctx.createLinearGradient(0, 0, 0, chartHeight);
    bgGradient.addColorStop(0, '#ffffff');
    bgGradient.addColorStop(1, '#f7f9fa');
    ctx.fillStyle = bgGradient;
    ctx.fillRect(0, 0, width, chartHeight);

    // Отрисовка фона для постобработки
    const postProcessingSlice = postProcessingHistory.slice(postProcessingHistory.length - Math.ceil(width));
    for (let i = 0; i < postProcessingSlice.length; i++) {
        const value = postProcessingSlice[i];
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



    const recSlice = recHistory.slice(recHistory.length - Math.ceil(width));
    ctx.fillStyle = 'rgba(192, 57, 43, 0.2)';
    for (let i = 0; i < recSlice.length; i++) {
        const value = recSlice[i];
        if (value === 1) {
            const x = width - recSlice.length + i;
            ctx.fillRect(x, 0, 1, chartHeight);
        }
    }

    const drawWaveBackground = (history, color) => {
        const pointsToDraw = Math.min(history.length, Math.ceil(width));
        const historySlice = history.slice(history.length - pointsToDraw);

        ctx.beginPath();
        ctx.moveTo(width - pointsToDraw, chartHeight); 

        for (let i = 0; i < historySlice.length; i++) {
            const value = historySlice[i] || 0;
            const x = width - pointsToDraw + i;
            const y = chartHeight - Math.min(1, value * 1) * chartHeight;
            ctx.lineTo(x, y);
        }

        ctx.lineTo(width, chartHeight);
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

    const now = new Date();
    const endTime = now.getTime();
    const timePerPixel = 50;
    const startTime = endTime - width * timePerPixel;
    const seconds = now.getSeconds();
    const secondsUntilNextMark = seconds < 30 ? 30 - seconds : 60 - seconds;

    if (secondsUntilNextMark <= 20 && secondsUntilNextMark > 0) {
        const mskTime = now.toLocaleTimeString('ru-RU', { timeZone: 'Europe/Moscow', hour: '2-digit', minute: '2-digit', second: '2-digit' });
        const irkTime = now.toLocaleTimeString('ru-RU', { timeZone: 'Asia/Irkutsk', hour: '2-digit', minute: '2-digit', second: '2-digit' });

        ctx.textAlign = 'right';
        ctx.fillStyle = 'rgba(127, 140, 141, 0.5)';
        ctx.font = '500 18px Ubuntu, sans-serif';
        ctx.fillText(`МСК: ${mskTime}`, width - 5, height - 22);
        ctx.fillText(`ИРК: ${irkTime}`, width - 5, height - 2);
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
            ctx.font = '500 18px Ubuntu, sans-serif';
            ctx.textAlign = 'right';
            ctx.fillText(`МСК: ${mskTime}`, x - 5, height - 22);
            ctx.fillText(`ИРК: ${irkTime}`, x - 5, height - 2);
        } 
        else {
            ctx.strokeStyle = '#aaaaaa';
            ctx.lineWidth = 0.5;
            ctx.beginPath();
            ctx.moveTo(x, 0); ctx.lineTo(x, chartHeight);
            ctx.stroke();
        }

        lastMarkTime.setSeconds(lastMarkTime.getSeconds() - 5);
    }
    
    ctx.lineWidth = 1.5;
    
    const drawLine = (history, colorFunc) => {
        const pointsToDraw = Math.min(history.length, Math.ceil(width));
        const historySlice = history.slice(history.length - pointsToDraw);

        for (let i = 1; i < historySlice.length; i++) {
            const prevValue = historySlice[i - 1] || 0;
            const newValue = historySlice[i] || 0;

            const x1 = width - pointsToDraw + (i - 1);
            const x2 = width - pointsToDraw + i;
            
            ctx.beginPath();
            ctx.strokeStyle = typeof colorFunc === 'function' ? colorFunc(newValue) : colorFunc;
            ctx.moveTo(x1, chartHeight - Math.min(1, prevValue * 1) * chartHeight);
            ctx.lineTo(x2, chartHeight - Math.min(1, newValue * 1) * chartHeight);
            ctx.stroke();
        }
    };

    drawLine(sysHistory, '#3498db');
    drawLine(micHistory, value => value > 0.9 ? '#ff0000' : (value > 0.7 ? '#e74c3c' : '#c0392b'));
}

function renderLoop() {
    requestAnimationFrame(renderLoop);
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

        micHistory.push(amplifiedMic);
        sysHistory.push(amplifiedSys);
        recHistory.push(recValue);
        postProcessingHistory.push(postProcessingValue);
        if (micHistory.length > chartHistorySize) micHistory.shift();
        if (sysHistory.length > chartHistorySize) sysHistory.shift();
        if (recHistory.length > chartHistorySize) recHistory.shift();
        if (postProcessingHistory.length > chartHistorySize) postProcessingHistory.shift();

        if (frameCount % scrollInterval === 0) {
            redrawMovingChart();
        }
        frameCount++;
    } catch (error) {
        // console.error('Error fetching audio levels:', error);
    }
}

export function initChart() {
    if (!audioChartCanvas) return;
    
    micHistory = new Array(chartHistorySize).fill(0);
    sysHistory = new Array(chartHistorySize).fill(0);
    recHistory = new Array(chartHistorySize).fill(0);
    postProcessingHistory = new Array(chartHistorySize).fill(0);

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

    setInterval(updateAudioLevels, 50);
    renderLoop();
}

export { setupCanvas };
