/**
 * Gatekeeper Login Form Handler
 */

document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('login-form');
    const errorDiv = document.getElementById('login-error');
    const submitBtn = document.getElementById('login-btn');

    form.addEventListener('submit', async (e) => {
        e.preventDefault();

        // Clear previous errors
        errorDiv.classList.remove('visible');
        errorDiv.textContent = '';

        const email = document.getElementById('email').value.trim();
        const password = document.getElementById('password').value;

        if (!email || !password) {
            showError('Please enter both email and password.');
            return;
        }

        // Disable button while authenticating
        submitBtn.disabled = true;
        submitBtn.textContent = 'Signing in...';

        try {
            const response = await fetch('/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password })
            });

            const data = await response.json();

            if (response.ok && data.success) {
                // Redirect to admin panel
                window.location.href = data.redirect || '/admin';
            } else {
                showError(data.error || 'Authentication failed. Please check your credentials.');
            }
        } catch (err) {
            showError('Unable to connect to the server. Please try again.');
        } finally {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Sign In';
        }
    });

    function showError(message) {
        errorDiv.textContent = message;
        errorDiv.classList.add('visible');
    }
});
