const copyButton = document.getElementById('copy-install');
copyButton.hidden = false;
copyButton.addEventListener('click', async () => {
  const status = document.getElementById('copy-status');
  try {
    await navigator.clipboard.writeText(document.getElementById('install-prompt').textContent);
    status.textContent = copyButton.dataset.copied;
  } catch {
    status.textContent = copyButton.dataset.failed;
    document.querySelector('.prompt-preview').open = true;
  }
});
