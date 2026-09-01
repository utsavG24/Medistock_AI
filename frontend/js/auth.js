// ======================================================
// MEDISTOCK - AUTHENTICATION
// ======================================================

const AUTH_API_BASE = "http://127.0.0.1:8000";

function switchTab(tab) {
    document.getElementById("loginTab").classList.toggle("active", tab === "login");
    document.getElementById("signupTab").classList.toggle("active", tab === "signup");
    document.getElementById("loginSection").classList.toggle("active", tab === "login");
    document.getElementById("signupSection").classList.toggle("active", tab === "signup");
}

document.addEventListener("DOMContentLoaded", function () {

    // If arriving from a "Sign Up" link (e.g. home.html), open the signup tab directly
    const params = new URLSearchParams(window.location.search);
    if (params.get("tab") === "signup" && document.getElementById("signupTab")) {
        switchTab("signup");
    }

    const loginForm = document.getElementById("loginForm");
    if (loginForm) {
        loginForm.addEventListener("submit", async function (e) {
            e.preventDefault();
            const username = document.getElementById("loginUsername").value.trim();
            const password = document.getElementById("loginPassword").value;
            const messageEl = document.getElementById("loginMessage");
            messageEl.textContent = "";
            messageEl.className = "auth-message";

            try {
                const response = await fetch(`${AUTH_API_BASE}/auth/login`, {
                    method: "POST",
                    credentials: "include",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ username, password })
                });

                const data = await response.json();

                if (!response.ok) {
                    messageEl.textContent = data.detail || "Login failed.";
                    messageEl.classList.add("error");
                    return;
                }

                messageEl.textContent = "Login successful. Redirecting...";
                messageEl.classList.add("success");

                setTimeout(() => {
                    window.location.href = "index.html";
                }, 600);

            } catch (error) {
                console.error("Login error:", error);
                messageEl.textContent = "Unable to reach the server.";
                messageEl.classList.add("error");
            }
        });
    }

    const signupForm = document.getElementById("signupForm");
    if (signupForm) {
        signupForm.addEventListener("submit", async function (e) {
            e.preventDefault();
            const full_name = document.getElementById("signupFullName").value.trim();
            const username = document.getElementById("signupUsername").value.trim();
            const password = document.getElementById("signupPassword").value;
            const messageEl = document.getElementById("signupMessage");
            messageEl.textContent = "";
            messageEl.className = "auth-message";

            try {
                const response = await fetch(`${AUTH_API_BASE}/auth/signup`, {
                    method: "POST",
                    credentials: "include",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ username, password, full_name })
                });

                const data = await response.json();

                if (!response.ok) {
                    messageEl.textContent = data.detail || "Signup failed.";
                    messageEl.classList.add("error");
                    return;
                }

                messageEl.textContent = "Account created! You can now log in.";
                messageEl.classList.add("success");
                signupForm.reset();

                setTimeout(() => switchTab("login"), 1000);

            } catch (error) {
                console.error("Signup error:", error);
                messageEl.textContent = "Unable to reach the server.";
                messageEl.classList.add("error");
            }
        });
    }

});

// ======================================================
// AUTH GUARD - call this at the top of protected pages
// (include this same auth.js file, then call requireLogin())
// ======================================================

async function requireLogin() {
    try {
        const response = await fetch(`${AUTH_API_BASE}/auth/me`, {
            credentials: "include"
        });

        if (!response.ok) {
            window.location.href = "login.html";
            return null;
        }

        const data = await response.json();
        const adminNameEl = document.querySelector(".admin-info strong");
        if (adminNameEl) adminNameEl.textContent = data.full_name;

        return data;

    } catch (error) {
        console.error("Auth check failed:", error);
        window.location.href = "login.html";
        return null;
    }
}

async function logoutAdmin() {
    try {
        await fetch(`${AUTH_API_BASE}/auth/logout`, {
            method: "POST",
            credentials: "include"
        });
    } catch (error) {
        console.error("Logout error:", error);
    } finally {
        window.location.href = "login.html";
    }
}
