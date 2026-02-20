document.addEventListener('DOMContentLoaded', function () {
    // --- DOM Elements ---
    const statusIndicator = document.getElementById('status-indicator');
    const statusText = document.getElementById('status-text');
    const statusTime = document.getElementById('status-time');
    const postProcessStatus = document.getElementById('post-process-status');
    const recBtn = document.getElementById('rec-btn');
    const pauseBtn = document.getElementById('pause-btn');
    const stopBtn = document.getElementById('stop-btn');
    const pipBtn = document.getElementById('pip-btn');
    const favicon = document.getElementById('favicon');
    const volumeMetersContainer = document.querySelector('.volume-meters-container');

    // Скрываем кнопку PiP, если API не поддерживается
    if (!('documentPictureInPicture' in window)) {
        if (pipBtn) pipBtn.style.display = 'none';
    }

    // --- Tabs ---
    const tabLinks = document.querySelectorAll('.tab-link');
    const tabContents = document.querySelectorAll('.tab-content');

    tabLinks.forEach(link => {
        link.addEventListener('click', () => {
            const tabId = link.getAttribute('data-tab');

            tabLinks.forEach(l => l.classList.remove('active'));
            tabContents.forEach(c => c.classList.remove('active'));

            link.classList.add('active');
            document.getElementById(tabId).classList.add('active');
        });
    });

    // --- Recording Status and Controls ---
    let currentStatus = 'stop';
    let settings = {}; // Глобальная переменная для хранения настроек
    let audioContext;

    async function updateStatus() {
        try {
            const response = await fetch('/status');
            const data = await response.json();

            currentStatus = data.status;
            statusTime.textContent = `(${data.time})`;

            // Update status indicator and text
            statusIndicator.className = 'status-indicator ' + data.status;
            switch (data.status) {
                case 'rec':
                    statusText.textContent = 'Запись';                    
                    recBtn.textContent = 'REC'; // Убедимся, что текст кнопки правильный
                    volumeMetersContainer.classList.add('recording');
                    break;
                case 'paused':
                    statusText.textContent = 'Пауза';
                    recBtn.textContent = 'RESUME'; // Меняем текст кнопки на "RESUME" в режиме паузы
                    volumeMetersContainer.classList.remove('recording');
                    break;
                case 'stop':
                default:
                    statusText.textContent = 'Остановлено';
                    recBtn.textContent = 'REC'; // Возвращаем исходный текст
                    volumeMetersContainer.classList.remove('recording');
                    break;
            }

            // Update control buttons state
            recBtn.disabled = data.status === 'rec';
            pauseBtn.disabled = data.status !== 'rec';
            stopBtn.disabled = data.status === 'stop';
            
            // Update favicon
            favicon.href = `/favicon.ico?v=${new Date().getTime()}`;

            // Update post-processing status
            if (data.post_processing.active) {
                postProcessStatus.textContent = data.post_processing.info; // Показываем текст
            } else {
                postProcessStatus.innerHTML = '&nbsp;'; // Вставляем неразрывный пробел для сохранения высоты
            }

        } catch (error) {
            console.error('Error fetching status:', error);
            statusText.textContent = 'Ошибка соединения';
            statusIndicator.className = 'status-indicator stop';
        }
    }

    // Глобальный обработчик ошибок fetch для перенаправления на страницу входа
    document.addEventListener('fetch-error', function(e) {
        if (e.detail.status === 401) { window.location.href = '/login'; }
    });

    // --- Audio Level Charts ---
    const audioChartCanvas = document.getElementById('audio-chart');
    const audioChartCtx = audioChartCanvas.getContext('2d');
    
    // Сохраняем текущие размеры, чтобы избежать ненужных перерисовок при скролле на мобильных
    let currentCanvasWidth = 0;
    let currentCanvasHeight = 0;

    // --- Адаптация Canvas для HiDPI (Retina) дисплеев для четкости ---
    function setupCanvas(canvas) {
        const dpr = window.devicePixelRatio || 1;
        const rect = canvas.getBoundingClientRect();
        // Сохраняем новые размеры
        currentCanvasWidth = rect.width;
        currentCanvasHeight = rect.height;

        canvas.width = rect.width * dpr;
        canvas.height = rect.height * dpr;
        const ctx = canvas.getContext('2d');
        ctx.scale(dpr, dpr);
        return ctx;
    }

    // Перенастраиваем canvas при изменении размера окна
    window.addEventListener('resize', () => {
        // Перерисовываем, только если размеры действительно изменились
        const rect = audioChartCanvas.getBoundingClientRect();
        if (rect.width !== currentCanvasWidth || rect.height !== currentCanvasHeight) {
            setupCanvas(audioChartCanvas);
        }
    });
    // --- Конец адаптации ---

    const chartHistorySize = 6000; // 300 секунд * 20 обновлений/сек = 6000 точек
    let micHistory = new Array(chartHistorySize).fill(0);
    let sysHistory = new Array(chartHistorySize).fill(0);
    let recHistory = new Array(chartHistorySize).fill(0);

    function amplifyLevel(value) {
        return Math.sqrt(value);
    }

    let frameCount = 0;
    const scrollInterval = 1; // Уменьшаем до 1 для максимальной плавности (обновление каждые 50мс)

    // Переменные для плавного изменения цвета фона
    let currentBgR = 244, currentBgG = 247, currentBgB = 249;
    const colorChangeFactor = 0.1; // Фактор сглаживания (меньше = плавнее)

    // --- Новая, полностью переработанная функция отрисовки графика (v3) ---
    // Эта версия рисует временные метки, которые движутся вместе с графиком.
    function redrawMovingChart() {
        const canvas = audioChartCanvas;
        const dpr = window.devicePixelRatio || 1;
        const ctx = canvas.getContext('2d');

        // Логические размеры холста
        const width = canvas.width / dpr;
        const height = canvas.height / dpr;
        const chartHeight = height - 40; // Оставляем 40px для подписей

        // 1. Очищаем холст и рисуем приятный фоновый градиент
        ctx.clearRect(0, 0, width, height);

        // --- Расчет цвета для динамического фона всей страницы ---
        const currentMicLevel = micHistory[micHistory.length - 1] || 0;
        const currentSysLevel = sysHistory[sysHistory.length - 1] || 0;

        const micEffect = Math.min(1, currentMicLevel * 2.5);
        const sysEffect = Math.min(1, currentSysLevel * 2.5);

        // 1. Рассчитываем ЦЕЛЕВОЙ цвет на основе текущих уровней
        let targetR = 244, targetG = 247, targetB = 249; // Базовый цвет
        // Эффект микрофона (красноватый)
        targetR = targetR * (1 - micEffect) + 255 * micEffect;
        targetG = targetG * (1 - micEffect) + 210 * micEffect;
        targetB = targetB * (1 - micEffect) + 210 * micEffect;
        // Эффект системного звука (голубоватый)
        targetR = targetR * (1 - sysEffect) + 210 * sysEffect;
        targetG = targetG * (1 - sysEffect) + 225 * sysEffect;
        targetB = targetB * (1 - sysEffect) + 255 * sysEffect;

        // 2. Плавно переходим от ТЕКУЩЕГО цвета к ЦЕЛЕВОМУ
        currentBgR += (targetR - currentBgR) * colorChangeFactor;
        currentBgG += (targetG - currentBgG) * colorChangeFactor;
        currentBgB += (targetB - currentBgB) * colorChangeFactor;
        document.body.style.backgroundColor = `rgb(${Math.round(currentBgR)},${Math.round(currentBgG)},${Math.round(currentBgB)})`;

        const bgGradient = ctx.createLinearGradient(0, 0, 0, chartHeight);
        bgGradient.addColorStop(0, '#ffffff'); // Белый сверху
        bgGradient.addColorStop(1, '#f7f9fa'); // Возвращаем статичный светло-серый цвет для фона графика
        ctx.fillStyle = bgGradient;
        ctx.fillRect(0, 0, width, chartHeight);

        // --- Новый слой: индикатор записи ---
        const recSlice = recHistory.slice(recHistory.length - Math.ceil(width));
        ctx.fillStyle = 'rgba(192, 57, 43, 0.2)'; // Полупрозрачный красный
        for (let i = 0; i < recSlice.length; i++) {
            const value = recSlice[i];
            if (value === 1) {
                // Для каждой точки, где запись была активна, рисуем вертикальную линию шириной 1px.
                // Это эффективно создает сплошную область.
                const x = width - recSlice.length + i;
                ctx.fillRect(x, 0, 1, chartHeight);
            }
        }

        // --- Динамический фон на основе звуковых волн ---
        const drawWaveBackground = (history, color) => {
            const pointsToDraw = Math.min(history.length, Math.ceil(width));
            const historySlice = history.slice(history.length - pointsToDraw);

            ctx.beginPath();
            // Начинаем с левого нижнего угла видимой части
            ctx.moveTo(width - pointsToDraw, chartHeight); 

            for (let i = 0; i < historySlice.length; i++) {
                const value = historySlice[i] || 0;
                const x = width - pointsToDraw + i;
                const y = chartHeight - Math.min(1, value * 1) * chartHeight; // Уменьшаем усиление до x1
                ctx.lineTo(x, y);
            }

            // Завершаем путь в правом нижнем углу, чтобы создать замкнутую фигуру
            ctx.lineTo(width, chartHeight);
            ctx.closePath();

            ctx.fillStyle = color;
            ctx.fill();
        };
        drawWaveBackground(sysHistory, 'rgba(52, 152, 219, 0.08)'); // Полупрозрачный синий для системного звука
        drawWaveBackground(micHistory, 'rgba(231, 76, 60, 0.08)'); // Полупрозрачный красный для микрофона

        // 2. Рисуем горизонтальную сетку
        ctx.strokeStyle = '#aaaaaa'; // Сделаем горизонтальные линии темнее
        ctx.lineWidth = 0.5;
        for (let i = 1; i < 4; i++) {
            const y = chartHeight * (i / 4);
            ctx.beginPath();
            ctx.moveTo(0, y); ctx.lineTo(width, y);
            ctx.stroke();
        }

        // 3. Рисуем вертикальные временные метки, которые движутся с графиком
        const now = new Date();
        const endTime = now.getTime();
        const timePerPixel = 50; // 50 мс на пиксель (т.к. 1 точка = 1 пиксель)
        const startTime = endTime - width * timePerPixel;

        // --- Новая логика: Стационарная "призрачная" метка времени ---
        const seconds = now.getSeconds();
        const secondsUntilNextMark = seconds < 30 ? 30 - seconds : 60 - seconds;

        // Показываем "призрачную" метку за 20 секунд до события
        // и скрываем ее ровно в момент наступления :00 или :30.
        if (secondsUntilNextMark <= 20 && secondsUntilNextMark > 0) {
            // Показываем ТЕКУЩЕЕ время, а не будущее
            const mskTime = now.toLocaleTimeString('ru-RU', { timeZone: 'Europe/Moscow', hour: '2-digit', minute: '2-digit', second: '2-digit' });
            const irkTime = now.toLocaleTimeString('ru-RU', { timeZone: 'Asia/Irkutsk', hour: '2-digit', minute: '2-digit', second: '2-digit' });

            ctx.textAlign = 'right';
            ctx.fillStyle = 'rgba(127, 140, 141, 0.5)'; // Полупрозрачный цвет
            ctx.font = '18px sans-serif';
            ctx.font = '500 18px Ubuntu, sans-serif';
            ctx.fillText(`МСК: ${mskTime}`, width - 5, height - 22);
            ctx.fillText(`ИРК: ${irkTime}`, width - 5, height - 2);
        }

        // Находим последнюю 5-секундную отметку
        let lastMarkTime = new Date(endTime);
        lastMarkTime.setMilliseconds(0);
        lastMarkTime.setSeconds(Math.floor(lastMarkTime.getSeconds() / 5) * 5);

        // Идем в прошлое от последней отметки и рисуем все видимые линии
        while (lastMarkTime.getTime() >= startTime) {
            const timeDiff = endTime - lastMarkTime.getTime();
            const x = width - (timeDiff / timePerPixel);
            const markSeconds = lastMarkTime.getSeconds();

            // Каждые 30 секунд - жирная линия с подписью
            if (markSeconds === 0 || markSeconds === 30) {
                ctx.strokeStyle = '#aaaaaa'; // Унифицируем цвет
                ctx.lineWidth = 1; // Делаем линию толще
                ctx.beginPath();
                ctx.moveTo(x, 0); ctx.lineTo(x, chartHeight);
                ctx.stroke();
                // Добавляем секунды в отображение времени
                const mskTime = lastMarkTime.toLocaleTimeString('ru-RU', { timeZone: 'Europe/Moscow', hour: '2-digit', minute: '2-digit', second: '2-digit' });
                const irkTime = lastMarkTime.toLocaleTimeString('ru-RU', { timeZone: 'Asia/Irkutsk', hour: '2-digit', minute: '2-digit', second: '2-digit' });
                
                ctx.fillStyle = '#7f8c8d';
                ctx.font = '18px sans-serif';
                ctx.font = '500 18px Ubuntu, sans-serif';
                ctx.textAlign = 'right'; // Выравниваем по правому краю
                ctx.fillText(`МСК: ${mskTime}`, x - 5, height - 22); // Смещаем текст на 5px левее линии
                ctx.fillText(`ИРК: ${irkTime}`, x - 5, height - 2);
            } 
            // Каждые 5 секунд (кроме 30-секундных) - тонкая линия без подписи
            else {
                // Унифицируем цвет
                ctx.strokeStyle = '#aaaaaa';
                ctx.lineWidth = 0.5;
                ctx.beginPath();
                ctx.moveTo(x, 0); ctx.lineTo(x, chartHeight);
                ctx.stroke();
            }

            // Переходим к предыдущей 5-секундной отметке
            lastMarkTime.setSeconds(lastMarkTime.getSeconds() - 5);
        }
        
        // 4. Рисуем линии графиков
        ctx.lineWidth = 1.5;
        
        const drawLine = (history, colorFunc) => {
            // Определяем, сколько последних точек из истории нужно отрисовать
            const pointsToDraw = Math.min(history.length, Math.ceil(width));
            const historySlice = history.slice(history.length - pointsToDraw);

            for (let i = 1; i < historySlice.length; i++) {
                const prevValue = historySlice[i - 1] || 0;
                const newValue = historySlice[i] || 0;

                // `x` координата зависит от положения точки в видимой части истории
                const x1 = width - pointsToDraw + (i - 1);
                const x2 = width - pointsToDraw + i;
                
                ctx.beginPath();
                ctx.strokeStyle = typeof colorFunc === 'function' ? colorFunc(newValue) : colorFunc;
                ctx.moveTo(x1, chartHeight - Math.min(1, prevValue * 1) * chartHeight); // Уменьшаем усиление до x1
                ctx.lineTo(x2, chartHeight - Math.min(1, newValue * 1) * chartHeight); // Уменьшаем усиление до x1
                ctx.stroke();
            }
        };

        drawLine(sysHistory, '#3498db');
        drawLine(micHistory, value => value > 0.9 ? '#ff0000' : (value > 0.7 ? '#e74c3c' : '#c0392b')); // Только красные оттенки
    }
    // --- Конец функции отрисовки ---

    // --- Разделяем получение данных и отрисовку для плавности ---
    // Эта функция будет вызываться постоянно для плавной анимации
    function renderLoop() {
        // Логика отрисовки теперь полностью в updateAudioLevels,
        // чтобы синхронизировать данные и рендер.
        // Этот цикл остается для будущих анимаций, не связанных с данными,
        // и для стандартной практики requestAnimationFrame.
        requestAnimationFrame(renderLoop);
    }

    // Эта функция будет вызываться по интервалу для получения данных с сервера
    async function updateAudioLevels() {
        try {
            const response = await fetch('/audio_levels')
            if (response.status === 401) {
                // Если сессия истекла, перенаправляем на страницу входа
                window.location.href = '/login';
                return;
            }
            const levels = await response.json();
    
            const amplifiedMic = amplifyLevel(levels.mic < 0 ? 0 : levels.mic);
            const amplifiedSys = amplifyLevel(levels.sys < 0 ? 0 : levels.sys);
            const recValue = (currentStatus === 'rec') ? 1 : 0;

            // Добавляем проверку на существование массивов
            if (!micHistory) micHistory = new Array(chartHistorySize).fill(0);
            if (!sysHistory) sysHistory = new Array(chartHistorySize).fill(0);
    
            micHistory.push(amplifiedMic);
            sysHistory.push(amplifiedSys);
            recHistory.push(recValue);
            if (micHistory.length > chartHistorySize) micHistory.shift(); // Возвращаем старую логику
            if (sysHistory.length > chartHistorySize) sysHistory.shift(); // Возвращаем старую логику
            if (recHistory.length > chartHistorySize) recHistory.shift();

            // Вызываем отрисовку здесь, синхронно с получением данных
            // и только если frameCount кратен scrollInterval
            if (frameCount % scrollInterval === 0) {
                redrawMovingChart(); // Вызываем новую функцию отрисовки
            }
            frameCount++;
        } catch (error) {
            // console.error('Error fetching audio levels:', error); // Keep this commented to avoid console spam
        }
    }
    // --- Конец разделения ---


    // --- Picture-in-Picture (PiP) Logic ---
    let pipWindow = null;
    let chartPlaceholder = null; // Placeholder for the chart container
    let controlsPlaceholder = null; // Placeholder for the controls

    pipBtn.addEventListener('click', async () => {
        // Проверяем, поддерживается ли API
        if (!('documentPictureInPicture' in window)) {
            alert('Ваш браузер не поддерживает режим "Картинка в картинке" для HTML-элементов.');
            return;
        }

        // Если окно уже открыто, закрываем его
        if (pipWindow) {
            pipWindow.close();
            return;
        }

        try {
            // Запрашиваем новое окно PiP
            pipWindow = await window.documentPictureInPicture.requestWindow({
                width: audioChartCanvas.width / (window.devicePixelRatio || 1),
                height: audioChartCanvas.height / (window.devicePixelRatio || 1),
            });

            // --- Стилизация и наполнение PiP окна ---
            const pipDocument = pipWindow.document;
            const pipBody = pipDocument.body;
            pipDocument.title = "ChroniqueX Record Server"; // Устанавливаем заголовок для PiP окна

            // Копируем стили из основного документа
            [...document.styleSheets].forEach(styleSheet => {
                try {
                    const cssRules = [...styleSheet.cssRules].map(rule => rule.cssText).join('');
                    const style = pipDocument.createElement('style');
                    style.textContent = cssRules;
                    pipBody.appendChild(style);
                } catch (e) {
                    console.warn('Не удалось скопировать стили для PiP окна:', e);
                }
            });

            const controlsContainer = document.querySelector('.controls');

            const volumeChart = document.querySelector('.volume-chart');
            // Находим элементы статуса в основном окне и его клон для PiP
            const statusWrapper = document.querySelector('.status-wrapper');
            const mainHeader = document.querySelector('header');

            // --- Создаем заглушку для кнопок управления ---
            if (controlsContainer) {
                const computedStyle = window.getComputedStyle(controlsContainer);
                const controlsHeight = controlsContainer.offsetHeight;
                controlsPlaceholder = document.createElement('div');
                controlsPlaceholder.id = 'controls-placeholder';
                // Копируем высоту и все внешние отступы, чтобы избежать "подпрыгивания" макета
                controlsPlaceholder.style.height = `${controlsHeight}px`;
                controlsPlaceholder.style.marginTop = computedStyle.marginTop;
                controlsPlaceholder.style.marginBottom = computedStyle.marginBottom;
                controlsPlaceholder.style.marginLeft = computedStyle.marginLeft;
                controlsPlaceholder.style.marginRight = computedStyle.marginRight;
                // Вставляем заглушку перед кнопками, чтобы она заняла их место после перемещения
                controlsContainer.parentNode.insertBefore(controlsPlaceholder, controlsContainer);
            }

            // Скрываем легенду в режиме PiP
            const legendEl = volumeMetersContainer.querySelector('.chart-legend');
            if (legendEl) legendEl.style.display = 'none';

            // Заменяем контейнер графика на заглушку
            if (volumeMetersContainer) {
                chartPlaceholder = document.createElement('div');
                chartPlaceholder.id = 'pip-placeholder';
                chartPlaceholder.style.cssText = `
                    display: flex;
                    flex-direction: column;
                    justify-content: center;
                    align-items: center;
                    height: ${volumeMetersContainer.offsetHeight + 21}px;
                    box-sizing: border-box; /* Чтобы padding не увеличивал общую высоту */
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

            // Перемещаем график и кнопки в PiP окно
            // Применяем Flexbox для гибкой компоновки
            pipBody.style.display = 'flex';
            pipBody.style.flexDirection = 'column';
            pipBody.style.padding = '0';
            pipBody.style.overflow = 'hidden'; // Принудительно скрываем полосу прокрутки
            pipBody.style.margin = '0';
            if (statusWrapper) statusWrapper.style.alignItems = 'center'; // Центрируем контент внутри status-wrapper
            // Убираем лишние отступы у контейнеров, чтобы они не создавали скролл
            if (statusWrapper) statusWrapper.style.display = 'none'; // Скрываем оригинал, а не перемещаем
            if (volumeChart) volumeChart.style.margin = '0';
            if (volumeChart) volumeChart.style.width = '100%'; // Растягиваем график на всю ширину
            controlsContainer.style.padding = '10px 0'; // Добавляем отступы сверху и снизу кнопок
            const pipStatusWrapper = statusWrapper ? statusWrapper.cloneNode(true) : null;
            if (pipStatusWrapper) pipStatusWrapper.style.display = 'flex'; // Убедимся, что клон видим
            if (pipStatusWrapper) pipStatusWrapper.style.padding = '0 10px'; // Добавляем отступы для статуса в PiP
            controlsContainer.style.margin = '0';
            if (pipStatusWrapper) pipBody.append(pipStatusWrapper); // Перемещаем клон статуса в PiP окно
            if (volumeChart) pipBody.append(volumeChart);
            pipBody.append(controlsContainer);
            pipBtn.classList.add('active');

            // --- Адаптация размера графика при изменении размера PiP окна ---
            pipWindow.addEventListener('resize', () => {
                const pipDoc = pipWindow.document;
                if (!pipDoc) return;

                const controlsEl = pipDoc.querySelector('.controls'); // Блок с кнопками
                const statusEl = pipDoc.querySelector('.status-wrapper'); // Используем клон
                // const legendEl = pipDoc.querySelector('.chart-legend'); // Легенда теперь скрыта
                const canvasEl = pipDoc.getElementById('audio-chart'); // Сам холст

                if (!controlsEl || !legendEl || !canvasEl) return;

                // Вычисляем доступную высоту для холста
                const controlsHeight = controlsEl.offsetHeight;
                const statusHeight = statusEl ? statusEl.offsetHeight : 0;
                // Учитываем только отступы контейнера, так как легенда и gap между ней скрыты
                const controlsPadding = 0;
                const canvasBorder = 2; // 1px сверху + 1px снизу у самого canvas
                
                const totalNonCanvasHeight = controlsHeight + statusHeight + canvasBorder + controlsPadding;
                const availableHeight = pipDoc.documentElement.clientHeight - totalNonCanvasHeight;

                // Устанавливаем высоту, но не меньше минимального значения (например, 50px)
                canvasEl.style.height = `${Math.max(20, availableHeight)}px`;
                setupCanvas(canvasEl); // Перенастраиваем canvas с новыми размерами
            });

            // --- Обработка закрытия окна ---
            pipWindow.addEventListener('pagehide', () => {
                // Возвращаем элементы на основную страницу, используя сохраненные ссылки
                if (statusWrapper) statusWrapper.style.display = ''; // Показываем оригинал обратно
                
                // --- Восстанавливаем стили и размеры ---
                // Возвращаем легенду
                if (legendEl) legendEl.style.display = '';
                // Возвращаем контейнер графика на место заглушки
                if (chartPlaceholder && chartPlaceholder.parentNode) {
                    chartPlaceholder.parentNode.replaceChild(volumeMetersContainer, chartPlaceholder);
                }
                chartPlaceholder = null;
                // Возвращаем исходные стили для статуса
                if (statusWrapper) statusWrapper.style.alignItems = '';
                // Возвращаем график в его родительский контейнер
                if (volumeMetersContainer && volumeChart) {
                    volumeMetersContainer.prepend(volumeChart);
                }
                // Возвращаем исходные стили для отступов
                if (volumeChart) volumeChart.style.margin = '';
                if (volumeChart) volumeChart.style.width = ''; // Сбрасываем ширину
                // Сбрасываем высоту холста, чтобы он принял размеры из CSS
                const canvasEl = volumeMetersContainer.querySelector('#audio-chart');
                if (canvasEl) canvasEl.style.height = '';
                setupCanvas(audioChartCanvas); // Перенастраиваем холст под его оригинальные размеры
                controlsContainer.style.padding = '';
                // controlsContainer.style.margin = ''; // Этот стиль не менялся, сбрасывать не нужно
                controlsContainer.style.margin = ''; // Восстанавливаем margin, включая margin-bottom
                const mainControlsExtensions = document.querySelector('.main-controls-extensions');
                if (mainControlsExtensions) mainControlsExtensions.insertAdjacentElement('beforebegin', controlsContainer); // Возвращаем кнопки
                // Возвращаем кнопки на их место, заменяя заглушку
                if (controlsPlaceholder && controlsPlaceholder.parentNode) {
                    controlsPlaceholder.parentNode.replaceChild(controlsContainer, controlsPlaceholder);
                }
                controlsPlaceholder = null; // Сбрасываем заглушку

                pipBtn.classList.remove('active');
                pipWindow = null;
            });
        } catch (error) { console.error('Ошибка при открытии PiP окна:', error); }
    });

    

    // --- Recordings List and Actions ---
    const recordingsListContainer = document.getElementById('recordings-list');

    // Сохраняем состояние развернутых групп
    let expandedGroups = new Set();

    // --- Оптимизированное обновление списка записей ---
    let lastRecordingsState = 0;

    async function checkForRecordingUpdates() {
        try {
            const response = await fetch('/recordings_state');
            if (response.status === 401) {
                // Если сессия истекла, перенаправляем на страницу входа
                window.location.href = '/login';
                return;
            }
            const state = await response.json();
            if (state.last_modified > lastRecordingsState) {
                console.log('Обнаружены изменения в записях, обновляю список...');
                lastRecordingsState = state.last_modified;
                await updateRecordingsList();
            }
        } catch (error) {
            console.error('Ошибка при проверке состояния записей:', error);
        }
    }
    async function updateRecordingsList() {
        try {
            const response = await fetch('/get_date_dirs');
            if (response.status === 401) {
                // Если сессия истекла, перенаправляем на страницу входа
                window.location.href = '/login';
                return;
            }
            const dateGroupsData = await response.json();

            if (dateGroupsData.length === 0 && recordingsListContainer.children.length === 0) {
                recordingsListContainer.innerHTML = '<p>Записей пока нет.</p>';
                return;
            }

            // Группируем даты по неделям
            const weeks = {};
            dateGroupsData.forEach(group => {
                const year = new Date(group.date).getFullYear();
                const weekId = `${year}-W${group.week_number}`;
                if (!weeks[weekId]) {
                    weeks[weekId] = {
                        id: weekId,
                        year: year,
                        number: group.week_number,
                        header_text: group.week_header_text, // Сохраняем новый текст заголовка
                        dates: []
                    };
                }
                weeks[weekId].dates.push(group);
            });

            // Очищаем контейнер и рендерим заново. Это проще, чем сложная логика сравнения.
            recordingsListContainer.innerHTML = '';

            // Сортируем недели по убыванию
            const sortedWeekKeys = Object.keys(weeks).sort().reverse();

            for (const [index, weekId] of sortedWeekKeys.entries()) {
                const weekData = weeks[weekId];
                const weekGroupEl = document.createElement('div');
                weekGroupEl.className = 'week-group';
                weekGroupEl.dataset.weekId = weekId;

                // Сворачиваем все недели, кроме первой (самой новой)
                if (index > 0) {
                    weekGroupEl.classList.add('collapsed');
                }

                // Разделяем заголовок на две части для выравнивания по краям
                const headerParts = weekData.header_text.split(' : ');
                const weekDateRange = headerParts[0] || '';
                const weekNumberText = headerParts[1] || '';

                weekGroupEl.innerHTML = `<h4><span class="expand-icon"></span><span class="week-title">${weekDateRange}</span><span class="week-number">${weekNumberText}</span></h4>`;

                recordingsListContainer.appendChild(weekGroupEl);

                // Сортируем даты внутри недели по возрастанию
                weekData.dates.sort((a, b) => a.date.localeCompare(b.date));

                // Рендерим группы дат внутри недели
                for (const groupData of weekData.dates) {
                    let groupEl = document.createElement('div');
                    groupEl.className = 'date-group';
                    // Если группа была развернута, сохраняем это состояние
                    if (expandedGroups.has(groupData.date)) {
                        groupEl.classList.remove('collapsed');
                    } else {
                        groupEl.classList.add('collapsed');
                    }
                    groupEl.dataset.date = groupData.date;
                    groupEl.innerHTML = `
                        <h3>
                            <div class="date-group-left">
                                <span class="expand-icon"></span><span class="date-group-title">${groupData.date_part}</span>
                            </div>
                            <span class="date-group-day">${groupData.day_of_week}</span>
                        </h3>
                    `;
                    
                    // Добавляем пустую таблицу, которая заполнится при раскрытии
                    const tableContainer = document.createElement('div');
                    tableContainer.innerHTML = `<div class="recording-table"><div class="recording-table-header"><div class="recording-cell cell-time">Начало</div><div class="recording-cell cell-duration">Длит.</div><div class="recording-cell cell-title">Наименование</div><div class="recording-cell cell-files">Файлы</div></div><div class="recording-table-body"></div></div>`;
                    groupEl.appendChild(tableContainer);
                    weekGroupEl.appendChild(groupEl);
                }
                
                // После рендеринга всех групп дат для недели, проходимся по ним еще раз,
                // чтобы загрузить данные для тех, что были развернуты.
                for (const groupData of weekData.dates) {
                    if (expandedGroups.has(groupData.date)) {
                        const groupEl = weekGroupEl.querySelector(`.date-group[data-date="${groupData.date}"]`);
                        if (groupEl) await loadRecordingsForGroup(groupEl, groupData.date);
                    }
                }
            }
        } catch (error) {
            console.error('Error updating recordings list:', error);
        }
    }

    async function loadRecordingsForGroup(groupEl, date) {
        const tableBody = groupEl.querySelector('.recording-table-body');
        tableBody.innerHTML = '<div class="loading-placeholder">Загрузка...</div>'; // Показываем индикатор загрузки

        try {
            const response = await fetch(`/get_recordings_for_date/${date}`);
            if (response.status === 401) {
                // Если сессия истекла, перенаправляем на страницу входа
                window.location.href = '/login';
                return;
            }
            const recordings = await response.json();

            tableBody.innerHTML = ''; // Очищаем

            if (recordings.length === 0) {
                listEl.innerHTML = '<li class="loading-placeholder">В этой дате нет записей.</li>';
                return;
            }

            recordings.forEach(rec => {
                const audioExtension = rec.filename.split('.').pop().toUpperCase();
                const rowEl = document.createElement('div');
                rowEl.className = 'recording-table-row';
                rowEl.innerHTML = `
                    <div class="recording-cell cell-time">${rec.time}</div>
                    <div class="recording-cell cell-duration">${Math.floor(rec.duration / 60)} м ${Math.round(rec.duration % 60)} с</div>
                    <div class="recording-cell cell-title"><span class="editable-title" data-date="${date}" data-filename="${rec.filename}" data-prompt-addition="${escapeHtml(rec.promptAddition)}">${rec.title}</span></div>
                    <div class="recording-cell cell-files">
                        <a href="/files/${date}/${rec.filename}" target="_blank" class="action-btn audio-link">${audioExtension}</a>
                        <span class="file-action-pair">
                            <a href="/files/${date}/${rec.transcription_filename}" target="_blank" class="action-btn transcription-link ${rec.transcription_exists ? 'exists' : ''}">TXT</a>
                            <span class="recreate-actions-container"><button class="action-btn recreate-transcription-btn" title="Пересоздать транскрипцию" data-date="${date}" data-filename="${rec.filename}">&#x21bb;</button></span>
                        </span>
                        <span class="file-action-pair">
                            <a href="/files/${date}/${rec.protocol_filename}" target="_blank" class="action-btn protocol-link ${rec.protocol_exists ? 'exists' : ''}">PDF</a>
                            <span class="recreate-actions-container"><button class="action-btn recreate-protocol-btn" title="Пересоздать протокол" data-date="${date}" data-filename="${rec.filename}">&#x21bb;</button></span>
                        </span>
                    </div>
                `;
                tableBody.appendChild(rowEl);
            });
        } catch (error) {
            tableBody.innerHTML = '<div class="loading-placeholder">Ошибка загрузки записей.</div>';
            console.error(`Error loading recordings for ${date}:`, error);
        }
    }

    // Функция для экранирования HTML
    function escapeHtml(unsafe) {
        if (typeof unsafe !== 'string') return '';
        return unsafe
             .replace(/&/g, "&amp;")
             .replace(/</g, "&lt;")
             .replace(/>/g, "&gt;")
             .replace(/"/g, "&quot;")
             .replace(/'/g, "&#039;");
    }

    // Используем делегирование событий для кнопок действий
    recordingsListContainer.addEventListener('click', async (e) => {
        const target = e.target;

        // --- Обработчик для редактирования названия ---
        if (target.classList.contains('editable-title')) {
            const { date, filename, promptAddition } = target.dataset;
            const currentTitle = target.textContent;
            const row = target.closest('.recording-table-row');

            const input = document.createElement('input');
            input.type = 'text';
            input.value = currentTitle;
            input.className = 'title-edit-input input-field';

            target.replaceWith(input);
            input.focus();
            input.select();

            // Создаем и показываем блок с promptAddition
            let promptRow = null;
            if (promptAddition) {
                promptRow = document.createElement('div');
                promptRow.className = 'prompt-display-row';
                const promptContent = document.createElement('div');
                promptContent.className = 'prompt-addition-display';
                // Используем <pre> для сохранения форматирования и переносов строк
                promptContent.innerHTML = `<pre>${escapeHtml(promptAddition)}</pre>`;
                promptRow.appendChild(promptContent);

                // Вставляем новую строку после текущей строки записи
                row.parentNode.insertBefore(promptRow, row.nextSibling);
            }

            // --- Глобальный обработчик для выхода из режима редактирования ---
            const handleOutsideClick = (event) => {
                // Проверяем, был ли клик вне инпута, строки и блока с промптом
                const isClickInsideRow = row.contains(event.target);
                const isClickInsidePrompt = promptRow ? promptRow.contains(event.target) : false;

                if (!isClickInsideRow && !isClickInsidePrompt) {
                    saveTitle(); // Сохраняем и выходим из режима редактирования
                    // Удаляем обработчик после использования
                    document.removeEventListener('mousedown', handleOutsideClick);
                }
            };
            // Добавляем обработчик, когда входим в режим редактирования
            document.addEventListener('mousedown', handleOutsideClick);

            const saveTitle = async () => {
                const newTitle = input.value.trim();
                if (newTitle && newTitle !== currentTitle) {
                    // Обновляем data-атрибут, если нужно
                    target.dataset.promptAddition = promptAddition;
                    // Отправляем запрос на сервер
                    await fetch(`/update_metadata/${date}/${filename}`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ title: newTitle })
                    });
                    target.textContent = newTitle;
                } else {
                    target.textContent = currentTitle;
                }
                input.replaceWith(target);
                if (promptRow) promptRow.remove();
                // Убедимся, что глобальный обработчик удален при выходе
                document.removeEventListener('mousedown', handleOutsideClick);
            };

            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    input.blur();
                } else if (e.key === 'Escape') {
                    target.textContent = currentTitle;
                    if (promptRow) promptRow.remove();
                    // Убедимся, что глобальный обработчик удален при выходе
                    document.removeEventListener('mousedown', handleOutsideClick);
                    input.replaceWith(target);
                }
            });
        }

        // Обработчики для кнопок пересоздания теперь в функции `handleAction`
        if (target.classList.contains('recreate-transcription-btn')) {
            handleAction('recreate_transcription', target.dataset);
        } else if (target.classList.contains('recreate-protocol-btn')) {
            handleAction('recreate_protocol', target.dataset);
        }
        // Обработчик для разворачивания/сворачивания группы ДНЯ
        const groupHeader = e.target.closest('.date-group > h3');
        if (groupHeader) {
            const groupEl = groupHeader.parentElement;
            const date = groupEl.dataset.date;
            groupEl.classList.toggle('collapsed');
            if (!groupEl.classList.contains('collapsed')) {
                expandedGroups.add(date);
                await loadRecordingsForGroup(groupEl, date);
            } else {
                expandedGroups.delete(date);
            }
        }

        // Обработчик для сворачивания/разворачивания НЕДЕЛИ
        const weekHeader = e.target.closest('.week-group > h4');
        if (weekHeader) {
            const weekGroupEl = weekHeader.parentElement;
            weekGroupEl.classList.toggle('collapsed');
        }
    });

    // --- Settings Tab ---
    const settingsForm = document.getElementById('settings-form');
    const settingsSaveStatus = document.getElementById('settings-save-status');
    const addContextRuleBtn = document.getElementById('add-context-rule-btn');
    const addMeetingDateCheckbox = document.getElementById('add-meeting-date');
    const meetingDateSourceGroup = document.getElementById('meeting-date-source-group');
    const meetingNameTemplatesContainer = document.getElementById('meeting-name-templates-container');
    const confirmPromptOnActionCheckbox = document.getElementById('confirm-prompt-on-action');
    const addMeetingNameTemplateBtn = document.getElementById('add-meeting-name-template-btn');

    async function loadSettings() {
        const response = await fetch('/get_web_settings');
        settings = await response.json(); // Обновляем глобальную переменную
        document.getElementById('use-custom-prompt').checked = settings.use_custom_prompt;
        document.getElementById('prompt-addition').value = settings.prompt_addition;
        addMeetingDateCheckbox.checked = settings.add_meeting_date;
        const dateSourceRadio = document.querySelector(`input[name="meeting_date_source"][value="${settings.meeting_date_source}"]`);
        if (dateSourceRadio) dateSourceRadio.checked = true;
        confirmPromptOnActionCheckbox.checked = settings.confirm_prompt_on_action;

        renderMeetingNameTemplates(settings.meeting_name_templates, settings.active_meeting_name_template_id);
        toggleMeetingDateSourceVisibility();
        renderContextFileRules(settings.context_file_rules);
        updatePromptPreview();
    }

    async function saveSettings(keysToSave = null) {
        // Используем унифицированную функцию для сбора настроек с основной страницы
        const currentSettings = getSettingsFromDOM(document);
        
        let settingsToSave = currentSettings;
        // Если передан массив ключей, отправляем только их
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
    
        // По запросу пользователя убираем уведомление о сохранении
        // const result = await response.json();
        // settingsSaveStatus.textContent = result.message;
        // settingsSaveStatus.style.color = response.ok ? 'green' : 'red';
        // setTimeout(() => settingsSaveStatus.textContent = '', 3000);
    }

    // Автосохранение при изменении настроек
    document.getElementById('use-custom-prompt').addEventListener('change', () => { saveSettings(['use_custom_prompt']).then(updatePromptPreview); });
    // Для textarea используем 'change', чтобы не отправлять запрос на каждое нажатие клавиши
    document.getElementById('prompt-addition').addEventListener('input', () => { saveSettings(['prompt_addition']).then(updatePromptPreview); }); 
    addMeetingDateCheckbox.addEventListener('change', () => {
        toggleMeetingDateSourceVisibility();
        saveSettings(['add_meeting_date']).then(updatePromptPreview);
    });
    document.querySelectorAll('input[name="meeting_date_source"]').forEach(radio => {
        radio.addEventListener('change', () => { saveSettings(['meeting_date_source']).then(updatePromptPreview); });
    });

    function toggleMeetingDateSourceVisibility() { meetingDateSourceGroup.style.display = addMeetingDateCheckbox.checked ? 'block' : 'none'; }

    if (confirmPromptOnActionCheckbox) {
        confirmPromptOnActionCheckbox.addEventListener('change', () => {
            saveSettings(['confirm_prompt_on_action']);
        });
    }

    // --- Context File Rules ---
    const contextRulesContainer = document.getElementById('context-file-rules-container');

    function addContextRuleRow(pattern = '', prompt = '', isEnabled = true, container = contextRulesContainer) {
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
            saveSettings().then(updatePromptPreview);
        });

        // Автосохранение при изменении полей
        ruleItem.querySelector('.context-rule-enabled').addEventListener('change', () => { saveSettings(['context_file_rules']).then(updatePromptPreview); });
        ruleItem.querySelector('.context-rule-pattern').addEventListener('input', () => { saveSettings(['context_file_rules']).then(updatePromptPreview); });
        ruleItem.querySelector('.context-rule-prompt').addEventListener('input', () => { saveSettings(['context_file_rules']).then(updatePromptPreview); });

        container.appendChild(ruleItem);
        return ruleItem; // Возвращаем созданный элемент для дальнейшей работы
    }

    function renderContextFileRules(rules = []) {
        contextRulesContainer.innerHTML = '';
        if (rules.length === 0) {
            // Добавляем правило по умолчанию, если список пуст
            rules.push({ pattern: '*.html', prompt: '\n--- НАЧАЛО файла @{filename} ---\n{content}\n--- КОНЕЦ файла @{filename} ---\n', enabled: true });
        }
        rules.forEach(rule => {
            addContextRuleRow(rule.pattern, rule.prompt, rule.enabled);
        });
    }



    // --- Prompt Preview ---
    const promptPreviewContainer = document.getElementById('prompt-preview-container');
    const promptPreviewContent = document.getElementById('prompt-preview-content');

    // --- Логика сворачивания/разворачивания предпросмотра ---
    if (promptPreviewContainer) {
        const header = promptPreviewContainer.querySelector('h4');
        if (header) {
            // Добавляем иконку-стрелочку в заголовок
            header.insertAdjacentHTML('afterbegin', '<span class="expand-icon"></span>');
            // Сворачиваем по умолчанию
            promptPreviewContainer.classList.add('collapsed');

            header.addEventListener('click', () => {
                promptPreviewContainer.classList.toggle('collapsed');
            });
        }
    }

    async function updatePromptPreview() {
        try {
            // Используем унифицированную функцию для сбора настроек и отправки на предпросмотр
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

    

    addContextRuleBtn.addEventListener('click', () => {
        addContextRuleRow('', '', true);
    });

    // --- Meeting Name Templates ---
    function renderMeetingNameTemplates(templates = [], activeId = null) {
        meetingNameTemplatesContainer.innerHTML = '';

        // "Не добавлять" option
        const noneOption = createMeetingNameTemplateRow({ id: 'null', template: 'Не добавлять' }, activeId, false);
        meetingNameTemplatesContainer.appendChild(noneOption);

        templates.forEach(template => {
            const templateRow = createMeetingNameTemplateRow(template, activeId, true);
            meetingNameTemplatesContainer.appendChild(templateRow);
        });
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

    addMeetingNameTemplateBtn.addEventListener('click', () => {
        const newId = `template-${Date.now()}`;
        const newTemplate = { id: newId, template: '' };
        const newRow = createMeetingNameTemplateRow(newTemplate, null, true);
        meetingNameTemplatesContainer.appendChild(newRow);
        // Focus on the new input
        newRow.querySelector('.meeting-name-template-input').focus();
    });


    settingsForm.addEventListener('submit', (e) => e.preventDefault()); // Предотвращаем стандартную отправку формы
    
    // --- Contacts Tab ---
    const contactsContentWrapper = document.getElementById('contacts-content-wrapper');
    const contactsListContainer = contactsContentWrapper.querySelector('#contacts-list-container');
    const newGroupNameInput = document.getElementById('new-group-name');
    const addGroupBtn = document.getElementById('add-group-btn');

    function setRandomGroupPlaceholder() {
        const adjectives = [
            'Лысый', 'Грустный', 'Танцующий', 'Летающий', 'Пьяный',
            'Голодный', 'Задумчивый', 'Испуганный', 'Счастливый',
            'Прыгающий', 'Влюблённый', 'Уставший', 'Безумный',
            'Сердитый', 'Летающий задом наперёд', 'Танцующий ламбаду'
        ];

        const nouns = [
            // Все мужского рода
            'Хомяк', 'Пингвин', 'Картофель', 'Утюг', 'Кактус',
            'Огурец', 'Носок', 'Тапок', 'Холодильник', 'Чайник',
            'Ботинок', 'Банан', 'Пульт', 'Коврик', 'Батон',
            'Веник', 'Ёршик', 'Тазик', 'Кабачок', 'Бублик',
            'Робот', 'Ананас', 'Ниндзя', 'Монитор', 'Принтер'
        ];
        const getRandomItem = (arr) => arr[Math.floor(Math.random() * arr.length)];
        const adjective = getRandomItem(adjectives);
        const noun = getRandomItem(nouns);

        newGroupNameInput.placeholder = `Новая группа: ${adjective} ${noun}`;
    }

    let contactsData = {};
    let selectedContactIds = [];

    async function loadContactsAndSettings() {
        const [contactsRes, settingsRes] = await Promise.all([fetch('/get_contacts'), fetch('/get_web_settings')]);
        contactsData = await contactsRes.json();
        const settings = await settingsRes.json();
        selectedContactIds = settings.selected_contacts || [];
        renderContacts();
        renderMeetingNameTemplates(settings.meeting_name_templates, settings.active_meeting_name_template_id);
        renderContextFileRules(settings.context_file_rules);
        updatePromptPreview();
        updateSelectedContactsCount();
    }

    function renderContacts() {
        contactsListContainer.innerHTML = '';

        if (!contactsData.groups || contactsData.groups.length === 0) {
            contactsListContainer.insertAdjacentHTML('beforeend', '<p>Список участников пуст. Создайте первую группу.</p>');
            return;
        }

        function generateRandomPlaceholder() {
            const names = ['Иван', 'Борис', 'Анна', 'Семён', 'Максим', 'Людмила', 'Геннадий', 'Ольга', 'Виктор', 'Наталья', 'Пётр', 'Зинаида', 'Руслан', 'Эльвира', 'Дмитрий', 'Клавдия', 'Аркадий', 'Татьяна', 'Юрий', 'Фёдор'];
            const patronymics = ['Вилкович', 'Борисович', 'Ананасович', 'Семёнович', 'Максимович', 'Люциферович', 'Генераторович', 'Огурцовович', 'Викторович', 'Носкович', 'Петрович', 'Закусонович', 'Рулетович', 'Эскимосович', 'Дмитриевич', 'Котлетович', 'Арбузович', 'Тапочкович', 'Юрьевич', 'Фёдорович'];
            const surnames = ['Ложкин', 'Бублик', 'Ананасов', 'Семечкин', 'Максимум', 'Лепёшкин', 'Глюкозов', 'Окрошка', 'Винегретов', 'Носков', 'Пельмёнов', 'Заливной', 'Рулетов', 'Эскимосов', 'Дырявин', 'Котлетов', 'Арбузов', 'Тапкин', 'Юморов', 'Фантазёров'];
            const positions = ['программист', 'бухгалтер', 'дизайнер', 'менеджер', 'аналитик', 'юрист', 'директор', 'редактор', 'тестировщик', 'администратор', 'инженер', 'маркетолог', 'консультант', 'куратор', 'архитектор', 'экономист', 'продюсер', 'секретарь', 'тренер', 'разработчик'];

            const getRandomItem = (arr) => arr[Math.floor(Math.random() * arr.length)];

            const name = getRandomItem(names);
            const patronymic = getRandomItem(patronymics);
            const surname = getRandomItem(surnames);
            const position = getRandomItem(positions);

            // Корректируем окончание фамилии и отчества для женских имен
            let finalSurname = surname;
            let finalPatronymic = patronymic;
            if (['Анна', 'Людмила', 'Ольга', 'Наталья', 'Зинаида', 'Эльвира', 'Клавдия', 'Татьяна'].includes(name)) {
                if (surname.endsWith('ов') || surname.endsWith('ин') || surname.endsWith('ев')) {
                    finalSurname += 'а';
                }
                if (patronymic.endsWith('ич')) {
                    finalPatronymic = patronymic.slice(0, -2) + 'на';
                }
            }

            return `${finalSurname} ${name} ${finalPatronymic} — ${position}`;
        }

        // Сортируем группы по имени (алфавиту)
        const sortedGroups = [...contactsData.groups].sort((a, b) => a.name.localeCompare(b.name, 'ru'));
        sortedGroups.forEach(group => {
            const groupEl = document.createElement('div');
            // Добавляем класс 'collapsed', чтобы группа была свернута по умолчанию
            groupEl.className = 'contact-group collapsed';

            const groupHeaderEl = document.createElement('div');
            groupHeaderEl.className = 'contact-group-header';

            const groupHeaderLabel = document.createElement('label');
            groupHeaderLabel.className = 'contact-group-header-label'; // Новый класс для стилизации
            const groupNameEl = document.createElement('h4');
            groupNameEl.className = 'contact-group-name';
            groupNameEl.textContent = group.name;

            // Создаем обертку для иконки, чтобы увеличить кликабельную область
            const expandIconWrapper = document.createElement('div');
            expandIconWrapper.className = 'expand-icon-wrapper';

            // Создаем саму иконку
            const expandIcon = document.createElement('span');
            expandIcon.className = 'expand-icon';
            expandIconWrapper.appendChild(expandIcon);
            groupHeaderEl.appendChild(expandIconWrapper);

            groupNameEl.style.cursor = 'text'; // Указываем, что текст можно редактировать

            const groupCheckbox = document.createElement('input');
            groupCheckbox.value = "";
            groupCheckbox.type = 'checkbox';
            groupCheckbox.title = 'Выбрать/снять всех в группе';
            
            // --- Счетчик участников ---
            const contactIdsInGroup = group.contacts.map(c => c.id);
            const totalCount = contactIdsInGroup.length;
            const selectedCount = contactIdsInGroup.filter(id => selectedContactIds.includes(id)).length;

            const groupCounterEl = document.createElement('span');
            groupCounterEl.className = 'group-counter';
            groupCounterEl.textContent = `${selectedCount} / ${totalCount}`;
            // --- Конец счетчика ---

            // Логика inline-редактирования для названия группы
            groupNameEl.addEventListener('click', () => {
                const oldName = group.name;
                const input = document.createElement('input');
                input.value = oldName;
                input.className = 'contact-name-edit input-field'; // Используем тот же стиль, что и для участника

                // Скрываем счетчик при редактировании
                if (groupHeaderEl.contains(groupCounterEl)) groupHeaderEl.removeChild(groupCounterEl);

                // Заменяем h4 на input
                groupHeaderLabel.replaceChild(input, groupNameEl);
                input.focus();
                input.select();

                // Создаем и добавляем кнопку удаления группы
                const deleteGroupBtn = document.createElement('button');
                deleteGroupBtn.textContent = '×';
                deleteGroupBtn.className = 'action-btn delete-btn';
                deleteGroupBtn.onmousedown = (e) => { // Используем mousedown, чтобы сработало до blur
                    e.preventDefault(); // Предотвращаем потерю фокуса с инпута
                    deleteGroup(oldName);
                };
                groupHeaderEl.appendChild(deleteGroupBtn);

                const saveChanges = async () => {
                    const newName = input.value.trim();
                    // Удаляем кнопку и возвращаем счетчик
                    groupHeaderEl.removeChild(deleteGroupBtn);
                    groupHeaderEl.appendChild(groupCounterEl);

                    // Если имя не изменилось или пустое, просто возвращаем h4
                    if (newName === oldName || !newName) {
                        groupHeaderLabel.replaceChild(groupNameEl, input);
                        updateGroupCounter(); // Обновляем счетчик на всякий случай
                        return;
                    }
                    // Отправляем запрос на сервер
                    const response = await fetch(`/groups/update`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ old_name: oldName, new_name: newName })
                    });

                    if (response.ok) {
                        // При успехе перезагружаем список, чтобы все обновилось
                        loadContactsAndSettings();
                    } else {
                        const result = await response.json();
                        alert(`Ошибка: ${result.message}`);
                        groupHeaderLabel.replaceChild(groupNameEl, input); // Возвращаем старое имя в случае ошибки
                    }
                };

                input.addEventListener('blur', saveChanges);
                input.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter') {
                        input.blur();
                    } else if (e.key === 'Escape') { 
                        // Возвращаем все как было
                        groupHeaderEl.appendChild(groupCounterEl);
                        groupHeaderEl.removeChild(deleteGroupBtn); // Удаляем кнопку
                        groupHeaderLabel.replaceChild(groupNameEl, input); // Возвращаем h4 без сохранения
                    }
                });
            });

            groupHeaderLabel.appendChild(groupCheckbox); // Чекбокс внутри label
            groupHeaderLabel.appendChild(groupNameEl);   // Имя группы внутри label

            groupHeaderEl.appendChild(groupHeaderLabel); // Label добавляется в заголовок
            groupHeaderEl.appendChild(groupCounterEl);   // Счетчик добавляется в заголовок
            groupEl.appendChild(groupHeaderEl);

            // Функция для обновления состояния группового чекбокса
            const updateGroupCheckboxState = () => {
                const checkedInGroup = contactIdsInGroup.filter(id => selectedContactIds.includes(id));
                groupCheckbox.checked = checkedInGroup.length === contactIdsInGroup.length && contactIdsInGroup.length > 0;
                groupCheckbox.indeterminate = checkedInGroup.length > 0 && checkedInGroup.length < contactIdsInGroup.length;
            };

            // Функция для обновления текста счетчика
            const updateGroupCounter = () => {
                const currentSelectedCount = contactIdsInGroup.filter(id => selectedContactIds.includes(id)).length;
                groupCounterEl.textContent = `${currentSelectedCount} / ${totalCount}`;
            };

            // Обработчик для группового чекбокса
            groupCheckbox.addEventListener('change', () => {
                handleGroupCheckboxChange(groupCheckbox.checked, contactIdsInGroup, updateGroupCounter);
            });

            const listEl = document.createElement('ul');
            listEl.className = 'contact-group-list';

            // Добавляем строку для добавления нового участника в группу (в начало списка)
            const addItemEl = document.createElement('li');
            addItemEl.className = 'add-item-row';

            const addInput = document.createElement('input');
            addInput.type = 'text';
            addInput.placeholder = `Новый учасник: ${generateRandomPlaceholder()}`;
            addInput.className = 'add-item-input input-field';
            const addBtn = document.createElement('button');
            addBtn.textContent = 'Добавить';
            addBtn.className = 'action-btn';
            addBtn.onclick = async () => {
                const name = addInput.value.trim();
                if (!name) {
                    alert('Имя участника не может быть пустым.');
                    return;
                }
                await fetch('/contacts/add', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name, group_name: group.name })
                });
                addInput.value = '';
                loadContactsAndSettings(); // Перезагружаем список
            };
            addInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') addBtn.click(); });

            addItemEl.appendChild(addInput);
            addItemEl.appendChild(addBtn);
            listEl.appendChild(addItemEl);

            // Сортируем контакты в группе по имени (алфавиту)
            const sortedContacts = [...group.contacts].sort((a, b) => a.name.localeCompare(b.name, 'ru'));

            sortedContacts.forEach(contact => {
                const itemEl = document.createElement('li');
                
                const labelEl = document.createElement('label');
                const checkbox = document.createElement('input');
                checkbox.type = 'checkbox';
                checkbox.value = contact.id;
                checkbox.checked = selectedContactIds.includes(contact.id);
                checkbox.addEventListener('change', () => {
                    saveContactSelection().then(updatePromptPreview); // Сохраняем выбор и обновляем предпросмотр
                    updateGroupCheckboxState(); // Обновляем состояние группового чекбокса
                    updateGroupCounter(); // Обновляем счетчик
                });

                labelEl.appendChild(checkbox);
                
                // Создаем span для имени, чтобы сделать его редактируемым
                const nameSpan = document.createElement('span');
                nameSpan.className = 'contact-name';
                nameSpan.textContent = contact.name;
                labelEl.appendChild(nameSpan);

                itemEl.appendChild(labelEl);

                listEl.appendChild(itemEl);

                // Логика inline-редактирования
                nameSpan.addEventListener('click', () => {
                    const currentName = nameSpan.textContent;
                    const input = document.createElement('input');
                    input.type = 'text';
                    input.value = currentName;
                    input.className = 'contact-name-edit input-field';

                    // Создаем кнопку удаления и контейнер для нее
                    const buttonsContainer = document.createElement('div');
                    buttonsContainer.className = 'item-actions';
                    const deleteBtn = document.createElement('button');
                    deleteBtn.textContent = '×';
                    deleteBtn.className = 'action-btn delete-btn';
                    // Используем mousedown, чтобы событие сработало до blur на поле ввода
                    deleteBtn.onmousedown = (e) => {
                        e.preventDefault(); // Предотвращаем потерю фокуса с поля ввода
                        deleteContact(contact.id, contact.name);
                    };
                    buttonsContainer.appendChild(deleteBtn);

                    // Заменяем span на input
                    labelEl.replaceChild(input, nameSpan);
                    // Вставляем контейнер с кнопкой после label
                    itemEl.appendChild(buttonsContainer);
                    input.focus();
                    input.select();

                    const saveChanges = async () => {
                        const newName = input.value.trim();
                        // Удаляем кнопку удаления
                        itemEl.removeChild(buttonsContainer);
                        // Если имя не изменилось или пустое, просто возвращаем span
                        if (newName === currentName || !newName) {
                            labelEl.replaceChild(nameSpan, input);
                            return;
                        }

                        // Отправляем запрос на сервер
                        await fetch(`/contacts/update/${contact.id}`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ name: newName })
                        });

                        // Обновляем имя в span и возвращаем его
                        nameSpan.textContent = newName;
                        labelEl.replaceChild(nameSpan, input);
                    };

                    // Сохраняем при потере фокуса
                    input.addEventListener('blur', saveChanges);

                    // Сохраняем по Enter, отменяем по Escape
                    input.addEventListener('keydown', (e) => {
                        if (e.key === 'Enter') {
                            input.blur();
                        } else if (e.key === 'Escape') {
                            // Удаляем кнопку и возвращаем span без сохранения
                            itemEl.removeChild(buttonsContainer);
                            labelEl.replaceChild(nameSpan, input);
                        }
                    });
                });
            });

            groupEl.appendChild(listEl);
            contactsListContainer.appendChild(groupEl);

            // Устанавливаем начальное состояние группового чекбокса
            updateGroupCheckboxState();

            // Обработчик для сворачивания/разворачивания только по клику на иконку
            expandIconWrapper.addEventListener('click', (e) => {
                e.stopPropagation(); // Предотвращаем всплытие события до других элементов
                groupEl.classList.toggle('collapsed');
            });

            // Добавляем такой же обработчик на счетчик, чтобы по нему тоже можно было сворачивать
            groupCounterEl.addEventListener('click', (e) => {
                e.stopPropagation(); // Предотвращаем всплытие события
                groupEl.classList.toggle('collapsed');
            });

            // Обработчик для клика по label (включая название группы), чтобы переключать чекбокс
            groupHeaderLabel.addEventListener('click', (e) => {
                // Игнорируем клики по самому чекбоксу (чтобы избежать двойного срабатывания) и полю редактирования
                if (e.target.tagName === 'INPUT' || e.target.classList.contains('contact-name-edit')) {
                    return;
                }

                // Определяем, нужно ли выбрать всех (true) или снять выбор (false).
                // Если выбраны не все (включая 0), то мы выбираем всех.
                // Если выбраны уже все, то мы снимаем выбор.
                const shouldBeChecked = groupCheckbox.indeterminate || !groupCheckbox.checked;
                handleGroupCheckboxChange(shouldBeChecked, contactIdsInGroup, updateGroupCounter);
            });
        });
    }

    function getSelectedContacts() {
        const selected = [];
        document.querySelectorAll('#contacts-list-container .contact-group-list li label input[type="checkbox"]:checked').forEach(cb => {
            // Убедимся, что у чекбокса есть значение (ID контакта), чтобы не считать групповые чекбоксы
            if (cb.value) {
                selected.push(cb.value);
            }
        });
        return selected;
    }

    async function saveContactSelection() {
        selectedContactIds = getSelectedContacts();
        updateSelectedContactsCount(); // Обновляем счетчик на вкладке
        const settings = { selected_contacts: selectedContactIds };

        // We only update the contacts, not the whole form
        await fetch('/save_web_settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings)
        });
    }
    
    // --- Функция для обновления счетчика на вкладке ---
    function updateSelectedContactsCount() {
        const countElement = document.getElementById('selected-contacts-count');
        if (countElement) {
            const count = selectedContactIds.length;
            countElement.textContent = count > 0 ? `(${count})` : '';
            // Добавим немного стиля, чтобы счетчик был заметнее
            countElement.style.color = '#3498db';
            countElement.style.fontWeight = 'normal';
        }
    }

    async function handleGroupCheckboxChange(isChecked, contactIdsInGroup, updateCounterCallback, container = document) {
        const allCheckboxes = container.querySelectorAll(`input[type="checkbox"]`);
        let selectionChanged = false;
        allCheckboxes.forEach(cb => {
            if (contactIdsInGroup.includes(cb.value)) {
                if (cb.checked !== isChecked) {
                    cb.checked = isChecked;
                    selectionChanged = true;
                }
            }
        });

        // Если мы в модальном окне, просто обновляем предпросмотр без сохранения на сервер.
        // Сохранение произойдет при нажатии "Подтвердить".
        if (container !== document) {
            return; // Выходим, чтобы не вызывать saveContactSelection
        }
        if (selectionChanged) await saveContactSelection().then(updatePromptPreview);

        // Обновляем счетчик после всех изменений
        if (updateCounterCallback) updateCounterCallback();
    }

    addGroupBtn.addEventListener('click', async () => {
        const groupName = newGroupNameInput.value.trim();
        if (!groupName) {
            alert('Имя группы не может быть пустым.');
            return;
        }

        // Просто добавляем контакт с пустым именем, чтобы сервер создал группу
        await fetch('/contacts/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: `_init_group_`, group_name: groupName })
        });

        newGroupNameInput.value = '';
        loadContactsAndSettings();
    });

    async function loadGroupNames() {
        try {
            const response = await fetch('/get_group_names');
            const groupNames = await response.json();
            const datalist = document.getElementById('group-names-list');
            if (datalist) {
                datalist.innerHTML = ''; // Очищаем старые опции
                groupNames.forEach(name => {
                    datalist.innerHTML += `<option value="${name}">`;
                });
            }
        } catch (error) { console.error('Error fetching group names:', error); }
    }

    async function deleteContact(id, name) {
        if (!confirm(`Вы уверены, что хотите удалить участника "${name}"?`)) {
            return;
        }
        await fetch(`/contacts/delete/${id}`, { method: 'POST' });
        loadContactsAndSettings();
    }

    async function deleteGroup(name) {
        if (!confirm(`Вы уверены, что хотите удалить группу "${name}" и всех ее участников?`)) {
            return;
        }
        await fetch(`/groups/delete`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name })
        });
        loadContactsAndSettings();
    }

    newGroupNameInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            addGroupBtn.click();
        }
    });

    // --- Confirmation Modal Logic ---
    const modal = document.getElementById('confirmation-modal');
    const modalConfirmBtn = document.getElementById('modal-confirm-btn');
    const modalCancelBtn = document.getElementById('modal-cancel-btn');
    const modalSettingsCol = document.getElementById('modal-settings-col');
    const modalContactsCol = document.getElementById('modal-contacts-col');
    const modalPreviewCol = document.getElementById('modal-preview-col');

    let onConfirmCallback = null;
    let modalPausedRecording = false; // Флаг, что модальное окно поставило запись на паузу

    function showConfirmationModal(onConfirm, newTemplateData = null) {
        onConfirmCallback = onConfirm;

        // 1. Клонируем содержимое вкладок
        const settingsContent = document.getElementById('settings-tab').cloneNode(true);
        const contactsContent = document.getElementById('contacts-content-wrapper').cloneNode(true);
        const previewContent = document.getElementById('prompt-preview-container').cloneNode(true);

        // 2. Очищаем колонки модального окна
        modalSettingsCol.innerHTML = '<h4>Настройки</h4>';
        modalContactsCol.innerHTML = '<h4>Участники</h4>';
        modalPreviewCol.innerHTML = '<h4>Предпросмотр</h4>';

        // 3. Вставляем клонированное содержимое
        modalSettingsCol.appendChild(settingsContent);
        modalContactsCol.appendChild(contactsContent);
        modalPreviewCol.appendChild(previewContent);

        // --- Удаляем ID у клонированных элементов, чтобы избежать конфликтов ---
        // ID должны быть уникальными на странице.
        settingsContent.querySelectorAll('[id]').forEach(el => {
            if (el.id !== 'settings-tab') el.removeAttribute('id');
        });

        // --- Добавляем новый сгенерированный шаблон названия собрания ---
        if (newTemplateData) {
            const templatesContainer = settingsContent.querySelector('#meeting-name-templates-container');
            if (templatesContainer) {
                const newRow = createMeetingNameTemplateRow(newTemplateData, newTemplateData.id, true);
                templatesContainer.querySelector('.meeting-name-template-item').insertAdjacentElement('afterend', newRow);
            }
        }

        // --- Разворачиваем предпросмотр по умолчанию ---
        const modalPreviewContainer = previewContent.closest('.prompt-preview-container');
        if (modalPreviewContainer) {
            modalPreviewContainer.classList.remove('collapsed');
        }

        // 4. Показываем модальное окно
        modal.style.display = 'flex';
        document.body.style.overflow = 'hidden'; // Блокируем прокрутку фона

        // 5. Переназначаем обработчики событий для клонированных элементов
        rebindModalEventListeners(modal);
    }

    function hideConfirmationModal() {
        modal.style.display = 'none';
        document.body.style.overflow = ''; // Восстанавливаем прокрутку

        // Если окно было отменено и оно ставило запись на паузу, возобновляем запись
        if (modalPausedRecording && onConfirmCallback) {
             fetch('/resume');
        }

        onConfirmCallback = null;
        modalPausedRecording = false; // Сбрасываем флаг
    }

    modalConfirmBtn.addEventListener('click', async () => {
        // Сохраняем все настройки из модального окна
        await saveModalSettings();

        if (onConfirmCallback) {
            onConfirmCallback();
        }
        hideConfirmationModal();
    });

    modalCancelBtn.addEventListener('click', hideConfirmationModal);

    // Закрытие модального окна по клику на фон
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            hideConfirmationModal();
        }
    });

    // --- Rebinding logic for cloned elements in modal ---
    // Эта функция должна быть расширена, чтобы покрыть все интерактивные элементы
    // Вспомогательная функция для сбора настроек из DOM (основного или модального)
    function getSettingsFromDOM(container = document) {
        const getVal = (selector) => container.querySelector(selector)?.value;
        const getChecked = (selector) => container.querySelector(selector)?.checked;

        const getContextFileRulesFromDOM = (cont) => {
            const rules = [];
            cont.querySelectorAll('.context-rule-item').forEach(item => {
                rules.push({
                    pattern: item.querySelector('.context-rule-pattern').value.trim(),
                    prompt: item.querySelector('.context-rule-prompt').value,
                    enabled: item.querySelector('.context-rule-enabled').checked
                });
            });
            return rules;
        };

        const getMeetingNameTemplatesFromDOM = (cont) => {
            const templates = [];
            cont.querySelectorAll('.meeting-name-template-item').forEach(item => {
                const id = item.dataset.id;
                if (!id || id === 'null') return; // Пропускаем опцию "Не добавлять"

                const templateInput = item.querySelector('input.meeting-name-template-input');
                if (templateInput) { // Редактируемый шаблон
                    templates.push({
                        id: id,
                        template: templateInput.value.trim()
                    });
                } else { // Нередактируемый шаблон (например, сгенерированный)
                    const label = item.querySelector('label');
                    if (label) {
                        templates.push({ id: id, template: label.textContent.trim() });
                    }
                }
            });
            return templates;
        };

        return {
            use_custom_prompt: getChecked('#use-custom-prompt'),
            prompt_addition: getVal('#prompt-addition'),
            add_meeting_date: getChecked('#add-meeting-date'),
            meeting_date_source: getVal('input[name="meeting_date_source"]:checked'),
            active_meeting_name_template_id: getVal('input[name="active_meeting_name_template"]:checked'),
            selected_contacts: [...container.querySelectorAll('.contact-group-list input[type="checkbox"]:checked')].map(cb => cb.value).filter(Boolean),
            context_file_rules: getContextFileRulesFromDOM(container),
            meeting_name_templates: getMeetingNameTemplatesFromDOM(container),
            confirm_prompt_on_action: getChecked('#confirm-prompt-on-action'),
        };
    }

    function rebindModalEventListeners(modal) {
        // --- Обновление предпросмотра в модальном окне ---
        const saveAndPreviewFromModal = async () => {
            const settingsFromModal = getSettingsFromDOM(modal);
            // 1. Сначала сохраняем настройки на сервер
            await fetch('/save_web_settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(settingsFromModal),
            });
            // 2. Затем запрашиваем предпросмотр с уже сохраненными настройками
            const response = await fetch('/preview_prompt_addition', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(settingsFromModal), // Отправляем те же данные для предпросмотра
            });
            const data = await response.json();
            const modalPreviewContent = modal.querySelector('#prompt-preview-content');
            if (modalPreviewContent) {
                modalPreviewContent.textContent = data.prompt_text || '';
            }
        };

        // --- Общие обработчики для сворачивания/разворачивания ---
        modal.querySelectorAll('.settings-group-header, .prompt-preview-container h4').forEach(header => {
            header.addEventListener('click', () => header.parentElement.classList.toggle('collapsed'));
        });

        // --- Обработчики для вкладки "Настройки" ---
        const rebindSettings = () => {
            // Все интерактивные элементы, влияющие на предпросмотр
            const elementsToRebind = [
                ...modal.querySelectorAll('#settings-tab input[type="checkbox"]'),
                ...modal.querySelectorAll('#settings-tab input[type="radio"]'),
                ...modal.querySelectorAll('#settings-tab textarea'),
                ...modal.querySelectorAll('#settings-tab input[type="text"]')
            ];
            elementsToRebind.forEach(el => {
                el.addEventListener('input', saveAndPreviewFromModal);
                el.addEventListener('change', saveAndPreviewFromModal);
            });

            // Восстанавливаем класс для группы с источником даты, так как ID был удален
            const dateSourceGroup = modal.querySelector('input[name="meeting_date_source"]')?.closest('.form-group');
            if (dateSourceGroup) {
                dateSourceGroup.classList.add('meeting-date-source-group');
            }

            // Отдельно привязываем обработчик для чекбокса даты, чтобы скрыть/показать зависимые радио-кнопки
            const addMeetingDateCheckbox = modal.querySelector('input[name="add_meeting_date"]');
            if (addMeetingDateCheckbox) {
                addMeetingDateCheckbox.addEventListener('change', () => {
                    modal.querySelector('.meeting-date-source-group').style.display = addMeetingDateCheckbox.checked ? 'block' : 'none';
                    saveAndPreviewFromModal();
                });
            }
            modal.querySelectorAll('input[name="meeting_date_source"]').forEach(radio => {
                radio.addEventListener('change', saveAndPreviewFromModal);
            });

            // Кнопки добавления/удаления правил
            modal.querySelectorAll('#settings-tab .remove-rule-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    btn.closest('.context-rule-item')?.remove();
                    saveAndPreviewFromModal();
                });
            });
            modal.querySelectorAll('#settings-tab .remove-template-btn').forEach(btn => {
                btn.onclick = () => {
                    btn.closest('.meeting-name-template-item')?.remove();
                    saveAndPreviewFromModal();
                };
            });

            // Кнопки "Добавить"
            modal.querySelector('#add-context-rule-btn')?.addEventListener('click', () => {
                const container = modal.querySelector('#context-file-rules-container');
                addContextRuleRow('', '', true, container); // Используем оригинальную функцию с указанием контейнера
                rebindSettings(); // Перепривязываем события для новой строки
            });
            modal.querySelector('#add-meeting-name-template-btn')?.addEventListener('click', () => {
                const container = modal.querySelector('#meeting-name-templates-container');
                const newId = `template-${Date.now()}`;
                // Вызываем оригинальную функцию для создания строки
                const newRow = createMeetingNameTemplateRow({ id: newId, template: '' }, null, true);
                container.appendChild(newRow);
                rebindSettings(); // Перепривязываем события для новой строки
            });
        };

        // --- Обработчики для вкладки "Участники" ---
        const rebindContacts = () => {
            modal.querySelectorAll('.contact-group').forEach(groupEl => {
                const expandIconWrapper = groupEl.querySelector('.expand-icon-wrapper');
                if (expandIconWrapper) {
                    expandIconWrapper.onclick = (e) => {
                        e.stopPropagation();
                        groupEl.classList.toggle('collapsed');
                    };
                }

                const groupCheckbox = groupEl.querySelector('.contact-group-header-label input[type="checkbox"]');
                const groupHeaderLabel = groupEl.querySelector('.contact-group-header-label');
                const contactIdsInGroup = [...groupEl.querySelectorAll('.contact-group-list input[type="checkbox"]')]
                                          .map(cb => cb.value).filter(Boolean);

                // --- Обработчик для группового чекбокса ---
                groupCheckbox.onchange = () => {
                    contactIdsInGroup.forEach(id => {
                        const cb = groupEl.querySelector(`input[value="${id}"]`);
                        if (cb) cb.checked = groupCheckbox.checked;
                    });
                    saveAndPreviewFromModal();
                };

                // --- Клик по заголовку имитирует клик по чекбоксу ---
                groupHeaderLabel.onclick = (e) => {
                    if (e.target.tagName !== 'INPUT' && !e.target.classList.contains('contact-name-edit')) {
                        groupCheckbox.click();
                    }
                };
            });

            modal.querySelectorAll('.contact-group-list input[type="checkbox"]').forEach(checkbox => {
                checkbox.onchange = () => {
                    const groupEl = checkbox.closest('.contact-group');
                    if (groupEl) {
                        const groupCheckbox = groupEl.querySelector('.contact-group-header-label input[type="checkbox"]');
                        const contactCheckboxes = [...groupEl.querySelectorAll('.contact-group-list input[type="checkbox"]')]
                                                  .filter(cb => cb.value);
                        const checkedCount = contactCheckboxes.filter(cb => cb.checked).length;
                        groupCheckbox.checked = checkedCount === contactCheckboxes.length && contactCheckboxes.length > 0;
                        groupCheckbox.indeterminate = checkedCount > 0 && checkedCount < contactCheckboxes.length;
                    }
                    saveAndPreviewFromModal();
                };
            });

            // Редактирование и удаление
            modal.querySelectorAll('.contact-name').forEach(nameSpan => {
                nameSpan.onclick = () => {
                    // Эта логика слишком сложна для простого переназначения,
                    // поэтому мы просто запрещаем редактирование в модальном окне.
                    // Пользователь может отредактировать на основной вкладке.
                    nameSpan.style.cursor = 'default';
                };
            });
            modal.querySelectorAll('.contact-group-name').forEach(nameSpan => {
                nameSpan.onclick = () => { nameSpan.style.cursor = 'default'; };
            });

            // Кнопка "Добавить" для группы
            modal.querySelector('#add-group-btn')?.addEventListener('click', () => {
                const input = modal.querySelector('#new-group-name');
                if (input.value.trim()) {
                    // Простое добавление пустой группы
                    const newGroupEl = document.createElement('div');
                    newGroupEl.className = 'contact-group';
                    newGroupEl.innerHTML = `<div class="contact-group-header"><h4>${input.value.trim()}</h4></div><ul class="contact-group-list"></ul>`;
                    modal.querySelector('#contacts-list-container').appendChild(newGroupEl);
                    input.value = '';
                }
            });
        };

        // Первичная привязка
        rebindSettings();
        rebindContacts();
        saveAndPreviewFromModal();
    }

    // Переопределяем функцию сохранения, чтобы она могла работать с DOM модального окна
    async function saveModalSettings() {
        const modal = document.getElementById('confirmation-modal');
        const settingsToSave = getSettingsFromDOM(modal);

        // Отдельно сохраняем контакты, так как они не входят в `saveSettings`
        await fetch('/save_web_settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ selected_contacts: settingsToSave.selected_contacts })
        });

        // Сохраняем остальные настройки
        await fetch('/save_web_settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settingsToSave)
        });
    }

    // --- Centralized Action Handler ---
    async function handleAction(action, params = {}) {
        const { date, filename } = params;

        let newMeetingTemplate = null;
        // Если останавливаем запись, генерируем новый шаблон названия
        if (action === 'stop' && currentStatus !== 'stop') {
            const startTimeText = statusTime.textContent.match(/\((\d{2}:\d{2}:\d{2})\)/);
            if (startTimeText) {
                const durationParts = startTimeText[1].split(':');
                const hours = parseInt(durationParts[0], 10);
                const minutes = parseInt(durationParts[1], 10);
                const seconds = parseInt(durationParts[2], 10);
                const now = new Date();
                const templateText = `${now.getHours()}.${String(now.getMinutes()).padStart(2, '0')} - ${minutes}м ${seconds}с`;

                newMeetingTemplate = { id: `generated-${Date.now()}`, template: templateText };
            }
        }

        // Получаем актуальное состояние чекбокса прямо из DOM
        const needsConfirmation = document.getElementById('confirm-prompt-on-action')?.checked || false;

        // Если нужно подтверждение и запись активна, ставим на паузу
        if (needsConfirmation && ['stop', 'recreate_transcription', 'recreate_protocol'].includes(action) && currentStatus === 'rec') {
            await fetch('/pause');
            modalPausedRecording = true;
        }

        const performAction = async () => {
            switch (action) {
                case 'stop':
                    await fetch('/stop');
                    break;
                case 'recreate_transcription':
                    await fetch(`/recreate_transcription/${date}/${filename}`);
                    alert(`Задача пересоздания транскрипции для ${filename} отправлена.`);
                    break;
                case 'recreate_protocol':
                    await fetch(`/recreate_protocol/${date}/${filename}`);
                    alert(`Задача пересоздания протокола для ${filename} отправлена.`);
                    break;
                case 'rec':
                    await fetch('/rec');
                    break;
                case 'resume':
                    await fetch('/resume');
                    break;
                case 'pause':
                    await fetch('/pause');
                    break;
            }
        };

        if (needsConfirmation && ['stop', 'recreate_transcription', 'recreate_protocol'].includes(action)) {
            showConfirmationModal(performAction, newMeetingTemplate);
        } else {
            await performAction();
        }
    }

    recBtn.addEventListener('click', () => handleAction(currentStatus === 'paused' ? 'resume' : 'rec'));
    pauseBtn.addEventListener('click', () => handleAction('pause'));
    stopBtn.addEventListener('click', () => handleAction('stop'));

    // --- Initialization ---
    function initialize() {
        updateStatus();
        setInterval(updateStatus, 2000); // Poll status every 2 seconds
        setInterval(checkForRecordingUpdates, 3000); // Проверяем обновления записей каждые 3 секунды
        setInterval(updateAudioLevels, 50); // Получаем данные об уровнях звука 20 раз в секунду
        updateRecordingsList(); // Загружаем список записей при инициализации
        setupCanvas(audioChartCanvas); // Первоначальная настройка canvas
        requestAnimationFrame(renderLoop); // Запускаем цикл отрисовки

        loadSettings();
        updatePromptPreview();
        loadContactsAndSettings();
        
        // Add click listeners to collapsible settings groups
        document.querySelectorAll('.settings-group-header').forEach(header => {
            header.addEventListener('click', () => {
                header.parentElement.classList.toggle('collapsed');
            });
        });
        setRandomGroupPlaceholder();
    }

    initialize();
});