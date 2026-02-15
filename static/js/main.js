document.addEventListener('DOMContentLoaded', function () {
    // --- DOM Elements ---
    const statusIndicator = document.getElementById('status-indicator');
    const statusText = document.getElementById('status-text');
    const statusTime = document.getElementById('status-time');
    const postProcessStatus = document.getElementById('post-process-status');
    const recBtn = document.getElementById('rec-btn');
    const pauseBtn = document.getElementById('pause-btn');
    const stopBtn = document.getElementById('stop-btn');
    const favicon = document.getElementById('favicon');

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
                    break;
                case 'pause':
                    statusText.textContent = 'Пауза';
                    break;
                case 'stop':
                default:
                    statusText.textContent = 'Остановлено';
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
                postProcessStatus.textContent = data.post_processing.info;
                postProcessStatus.style.display = 'block';
            } else {
                postProcessStatus.style.display = 'none';
            }

        } catch (error) {
            console.error('Error fetching status:', error);
            statusText.textContent = 'Ошибка соединения';
            statusIndicator.className = 'status-indicator stop';
        }
    }

    recBtn.addEventListener('click', () => fetch(currentStatus === 'pause' ? '/resume' : '/rec'));
    pauseBtn.addEventListener('click', () => fetch('/pause'));
    stopBtn.addEventListener('click', () => {
        fetch('/stop');
        // Optimistically reload the page to show the new file
        setTimeout(() => window.location.reload(), 2000);
    });

    // --- Action Buttons ---
    document.querySelectorAll('.recreate-transcription-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const { date, filename } = e.target.dataset;
            fetch(`/recreate_transcription/${date}/${filename}`);
            alert(`Задача пересоздания транскрипции для ${filename} запущена.`);
        });
    });

    document.querySelectorAll('.recreate-protocol-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const { date, filename } = e.target.dataset;
            fetch(`/recreate_protocol/${date}/${filename}`);
            alert(`Задача пересоздания протокола для ${filename} запущена.`);
        });
    });

    document.querySelectorAll('.compress-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const { date, filename } = e.target.dataset;
            fetch(`/compress_to_mp3/${date}/${filename}`);
            alert(`Процесс сжатия для ${filename} запущен. Страница перезагрузится через несколько секунд.`);
            setTimeout(() => window.location.reload(), 5000);
        });
    });

    // --- Settings Tab ---
    const settingsForm = document.getElementById('settings-form');
    const micVolumeSlider = document.getElementById('mic-volume');
    const micVolumeValue = document.getElementById('mic-volume-value');
    const sysAudioVolumeSlider = document.getElementById('sys-audio-volume');
    const sysAudioVolumeValue = document.getElementById('sys-audio-volume-value');
    const settingsSaveStatus = document.getElementById('settings-save-status');

    async function loadSettings() {
        const response = await fetch('/get_web_settings');
        const settings = await response.json();

        document.getElementById('use-custom-prompt').checked = settings.use_custom_prompt;
        document.getElementById('include-html-files').checked = settings.include_html_files;
        document.getElementById('prompt-addition').value = settings.prompt_addition;
        micVolumeSlider.value = settings.mic_volume_adjustment;
        sysAudioVolumeSlider.value = settings.system_audio_volume_adjustment;

        updateVolumeLabels();
    }

    function updateVolumeLabels() {
        micVolumeValue.textContent = micVolumeSlider.value > 0 ? `+${micVolumeSlider.value}` : micVolumeSlider.value;
        sysAudioVolumeValue.textContent = sysAudioVolumeSlider.value > 0 ? `+${sysAudioVolumeSlider.value}` : sysAudioVolumeSlider.value;
    }

    micVolumeSlider.addEventListener('input', updateVolumeLabels);
    sysAudioVolumeSlider.addEventListener('input', updateVolumeLabels);

    async function saveSettings() {
        const settings = {
            use_custom_prompt: document.getElementById('use-custom-prompt').checked,
            include_html_files: document.getElementById('include-html-files').checked,
            prompt_addition: document.getElementById('prompt-addition').value,
            mic_volume_adjustment: parseFloat(micVolumeSlider.value),
            system_audio_volume_adjustment: parseFloat(sysAudioVolumeSlider.value),
            // selected_contacts сохраняются отдельно при изменении на их вкладке
        };

        const response = await fetch('/save_web_settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings)
        });
    
        // По запросу пользователя убираем уведомление о сохранении
        // const result = await response.json();
        // settingsSaveStatus.textContent = result.message;
        // settingsSaveStatus.style.color = response.ok ? 'green' : 'red';
        // setTimeout(() => settingsSaveStatus.textContent = '', 3000);
    }

    // Автосохранение при изменении настроек
    document.getElementById('use-custom-prompt').addEventListener('change', saveSettings);
    document.getElementById('include-html-files').addEventListener('change', saveSettings);
    // Для textarea используем 'change', чтобы не отправлять запрос на каждое нажатие клавиши
    document.getElementById('prompt-addition').addEventListener('change', saveSettings); 
    // Для слайдеров используем 'change', чтобы отправлять запрос после отпускания мыши
    micVolumeSlider.addEventListener('change', saveSettings);
    sysAudioVolumeSlider.addEventListener('change', saveSettings);

    settingsForm.addEventListener('submit', (e) => e.preventDefault()); // Предотвращаем стандартную отправку формы

    // --- Contacts Tab ---
    const contactsListContainer = document.getElementById('contacts-list-container');
    const newGroupNameInput = document.getElementById('new-group-name');
    const addGroupBtn = document.getElementById('add-group-btn');

    function setRandomGroupPlaceholder() {
        const adjectives = [
            'Лысый', 'Грустный', 'Танцующий', 'Летающий', 'Пьяный',
            'Поющий', 'Бегающий', 'Мечтающий', 'Злой', 'Спящий',
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
    }

    function renderContacts() {
        contactsListContainer.innerHTML = '';

        // Создаем и добавляем строку для добавления новой группы в начало
        const addGroupRow = document.createElement('div');
        addGroupRow.className = 'add-item-row';
        addGroupRow.style.marginBottom = '15px';
        addGroupRow.style.paddingBottom = '15px';
        addGroupRow.style.borderBottom = '1px solid #e0e0e0';
        addGroupRow.appendChild(newGroupNameInput); // Перемещаем существующий инпут
        addGroupRow.appendChild(addGroupBtn); // Перемещаем существующую кнопку
        contactsListContainer.appendChild(addGroupRow);

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
                input.className = 'contact-name-edit'; // Используем тот же стиль, что и для участника

                // Скрываем счетчик при редактировании
                if (groupHeaderEl.contains(groupCounterEl)) groupHeaderEl.removeChild(groupCounterEl);

                // Заменяем h4 на input
                groupHeaderLabel.replaceChild(input, groupNameEl);
                input.focus();
                input.select();

                // Создаем и добавляем кнопку удаления группы
                const deleteGroupBtn = document.createElement('button');
                deleteGroupBtn.textContent = 'Удалить группу';
                deleteGroupBtn.className = 'action-btn delete-group-btn';
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
            addInput.className = 'add-item-input';
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
                    saveContactSelection(); // Сохраняем выбор
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
                    input.className = 'contact-name-edit';

                    // Создаем кнопку удаления и контейнер для нее
                    const buttonsContainer = document.createElement('div');
                    buttonsContainer.className = 'item-actions';
                    const deleteBtn = document.createElement('button');
                    deleteBtn.textContent = 'Удалить';
                    deleteBtn.className = 'action-btn';
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
        document.querySelectorAll('#contacts-list-container input[type="checkbox"]:checked').forEach(cb => {
            selected.push(cb.value);
        });
        return selected;
    }

    async function saveContactSelection() {
        selectedContactIds = getSelectedContacts();
        const settings = { selected_contacts: selectedContactIds };

        // We only update the contacts, not the whole form
        await fetch('/save_web_settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings)
        });
    }

    async function handleGroupCheckboxChange(isChecked, contactIdsInGroup, updateCounterCallback) {
        const groupCheckboxes = document.querySelectorAll(`input[type="checkbox"]`);
        let selectionChanged = false;
        groupCheckboxes.forEach(cb => {
            if (contactIdsInGroup.includes(cb.value)) {
                if (cb.checked !== isChecked) {
                    cb.checked = isChecked;
                    // Обновляем глобальный массив ID
                    selectionChanged = true;
                }
            }
        });

        // Сохраняем изменения, только если они были
        if (selectionChanged) await saveContactSelection();

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
            datalist.innerHTML = ''; // Очищаем старые опции
            groupNames.forEach(name => {
                datalist.innerHTML += `<option value="${name}">`;
            });
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

    // --- Initialization ---
    function initialize() {
        updateStatus();
        setInterval(updateStatus, 5000); // Poll status every 5 seconds
        loadSettings();
        loadContactsAndSettings();
        setRandomGroupPlaceholder();
    }

    initialize();
});