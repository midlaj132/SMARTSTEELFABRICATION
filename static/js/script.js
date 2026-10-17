document.addEventListener('DOMContentLoaded', function () {
    const mediaInput = document.querySelector('#media_files');
    const selectedFiles = document.querySelector('#selected-files');
    if (mediaInput && selectedFiles) {
        mediaInput.addEventListener('change', function () {
            const files = Array.from(mediaInput.files || []);
            if (files.length === 0) {
                selectedFiles.textContent = 'No files selected yet.';
                return;
            }
            const totalBytes = files.reduce(function (total, file) {
                return total + file.size;
            }, 0);
            const totalMb = (totalBytes / (1024 * 1024)).toFixed(1);
            selectedFiles.textContent = files.length + ' file(s) selected · ' + totalMb + ' MB total';
        });
    }

    document.querySelectorAll('form').forEach(function (form) {
        form.addEventListener('submit', function () {
            const submitButton = form.querySelector('button[type="submit"]');
            if (submitButton) {
                submitButton.disabled = true;
                const originalText = submitButton.textContent;
                submitButton.textContent = 'Processing...';
                setTimeout(function () {
                    submitButton.textContent = originalText;
                    submitButton.disabled = false;
                }, 2500);
            }
        });
    });
});
