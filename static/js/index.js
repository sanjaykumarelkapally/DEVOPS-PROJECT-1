// Index/Home page JavaScript - Dynamic form panel switching

document.addEventListener('DOMContentLoaded', function() {
    const scanTypeSelect = document.getElementById('scan_type');
    const scanForm = document.getElementById('dynamic_scan_form');
    const panels = document.querySelectorAll('.input-panel');
    const fields = {
        url: document.getElementById('url_input'),
        file: document.getElementById('file_input'),
        message: document.getElementById('message_input'),
    };

    const configs = {
        url: {
            action: '/search_with_url',
            enctype: 'multipart/form-data',
            field: fields.url,
            button: document.getElementById('scan_button_url'),
            buttonText: 'Search',
        },
        file: {
            action: '/search_with_file',
            enctype: 'multipart/form-data',
            field: fields.file,
            button: document.getElementById('scan_button_file'),
            buttonText: 'Scan',
        },
        message: {
            action: '/search_with_message',
            enctype: 'application/x-www-form-urlencoded',
            field: fields.message,
            button: document.getElementById('scan_button_message'),
            buttonText: 'Analyze',
        },
    };

    function setActivePanel(scanType) {
        panels.forEach((panel) => {
            const active = panel.dataset.panel === scanType;
            panel.classList.toggle('active', active);

            panel.querySelectorAll('input, textarea').forEach((input) => {
                input.required = active;
            });
        });

        const config = configs[scanType];
        scanForm.action = config.action;
        scanForm.enctype = config.enctype;
        config.button.textContent = config.buttonText;
        config.field.focus();
    }

    scanTypeSelect.addEventListener('change', (event) => {
        setActivePanel(event.target.value);
    });

    // Initialize with default panel
    setActivePanel(scanTypeSelect.value);
});
