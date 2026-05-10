const API_BASE = "";

const POLLING_INTERVAL = 60000; // 60 seconds

class SessionStats {
    constructor() {
        this.monthsToLoad = 6;
        this.maxOverallSessions = 1;
        this.totalSessionsCount = 0;
        this.totalSecondsCount = 0;
        this.allData = {}; // Store it globally for streak calculation
        this.refreshInterval = null; // To store the timer
    }


    startLiveUpdates(ms = POLLING_INTERVAL) {
        if (this.refreshInterval) clearInterval(this.refreshInterval);

        this.refreshInterval = setInterval(async () => {
            // Reset totals before recalculating from fresh data
            this.totalSessionsCount = 0;
            this.totalSecondsCount = 0;

            // Reload the core data and latest session
            await this.loadData();
            console.log("Stats updated live.");
        }, ms);
    }


    async loadData() {
        const now = new Date();
        let promises = [];
        let monthsInfo = [];

        // Queue up fetches for the last 6 months
        for (let i = 0; i < this.monthsToLoad; i++) {
            const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
            const year = d.getFullYear();
            const month = d.getMonth() + 1;
            monthsInfo.push({ year, month, dateObj: d });

            promises.push(
                fetch(`${API_BASE}/sessions/calendar?year=${year}&month=${month}`)
                    .then(res => res.json())
                    .catch(() => ({}))
            );
        }

        // Reset tracking variables before re-populating
        this.totalSessionsCount = 0;
        this.totalSecondsCount = 0;

        const results = await Promise.all(promises);

        results.forEach(data => {
            if (data && data.daily_data) {
                Object.assign(this.allData, data.daily_data);
                if (data.max_sessions > this.maxOverallSessions) {
                    this.maxOverallSessions = data.max_sessions;
                }

                for (const key in data.daily_data) {
                    this.totalSessionsCount += data.daily_data[key].count || 0;
                    this.totalSecondsCount += data.daily_data[key].total_time || 0;
                }
            }
        });

        this.updateHeroStats();
        this.renderVerticalCalendar(monthsInfo);
        // this.setupInteractions(); Note: Move setupInteractions to the constructor or a separate init
        // to prevent duplicate event listeners during live updates.
        await this.loadLatestSession();
    }

    async loadLatestSession() {
        const card = document.getElementById('recentSessionCard');
        if (!card) return;

        try {
            const res = await fetch(`${API_BASE}/sessions/latest`);
            if (!res.ok) {
                card.innerHTML = '<p style="color:#999;">No recent session yet.</p>';
                return;
            }

            const data = await res.json();
            if (!data || !data.task) {
                card.innerHTML = '<p style="color:#999;">No recent session yet.</p>';
                return;
            }

            const elapsed = Number(data.elapsed_time || 0);
            const h = Math.floor(elapsed / 3600);
            const m = Math.floor((elapsed % 3600) / 60);
            const s = elapsed % 60;
            const duration = `${h}h ${m}m ${s}s`;
            const ts = data.timestamp ? new Date(data.timestamp).toLocaleString() : 'Unknown date';

            card.innerHTML = `
                <div class="session-line">
                    <span>${data.task || 'Unnamed Session'}</span>
                    <span class="session-color" style="background: ${data.task_color || '#ccc'};"></span>
                </div>
                <div>Duration: ${duration}</div>
                <div>Completed: ${ts}</div>
                <div class="session-summary">${data.task_type || 'Meditation'} • ${data.subject || 'General'}</div>
            `;
        } catch (err) {
            console.error('Failed to load latest session:', err);
            card.innerHTML = '<p style="color:#999;">Unable to load latest session.</p>';
        }
    }

    calculateStreak() {
        let streak = 0;
        const now = new Date();
        // Start checking from exactly midnight local time today
        let checkDate = new Date(now.getFullYear(), now.getMonth(), now.getDate());

        // Helper to get formatted string for our allData dictionary
        const getStatsForDate = (d) => {
            const dateStr = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
            return this.allData[dateStr];
        };

        let todayStats = getStatsForDate(checkDate);

        // If today has 0 sessions, check yesterday.
        // (We don't punish the user if they just haven't done it yet today!)
        if (!todayStats || todayStats.count === 0) {
            checkDate.setDate(checkDate.getDate() - 1); // move back to yesterday
            let yesterdayStats = getStatsForDate(checkDate);

            if (!yesterdayStats || yesterdayStats.count === 0) {
                return 0; // No sessions today or yesterday means streak is 0
            }
        }

        // Count backwards day by day until we hit a day with no sessions
        while (true) {
            let stats = getStatsForDate(checkDate);
            if (stats && stats.count > 0) {
                streak++;
                checkDate.setDate(checkDate.getDate() - 1); // step back 1 day
            } else {
                break; // Gap found, streak ends
            }
        }

        return streak;
    }

    updateHeroStats() {
        document.getElementById('totalSessions').textContent = this.totalSessionsCount;

        const hours = Math.floor(this.totalSecondsCount / 3600);
        const minutes = Math.floor((this.totalSecondsCount % 3600) / 60);

        document.getElementById('totalHours').textContent = hours;
        document.getElementById('totalMinutes').textContent = String(minutes).padStart(2, '0');

        // Calculate and set the real streak!
        document.getElementById('currentStreak').textContent = this.calculateStreak();
    }

    renderVerticalCalendar(monthsInfo) {
        const container = document.getElementById('verticalHeatmap');
        container.innerHTML = '';

        const monthNames = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

        monthsInfo.forEach(info => {
            const firstDay = new Date(info.year, info.month - 1, 1);
            const lastDay = new Date(info.year, info.month, 0);
            const daysInMonth = lastDay.getDate();

            const jsDay = firstDay.getDay();
            const startOffset = jsDay === 0 ? 6 : jsDay - 1;

            const monthBlock = document.createElement('div');
            monthBlock.className = 'month-block';

            const label = document.createElement('div');
            label.className = 'month-label';
            label.textContent = monthNames[info.month - 1];
            monthBlock.appendChild(label);

            const grid = document.createElement('div');
            grid.className = 'month-grid';

            for (let i = 0; i < startOffset; i++) {
                const empty = document.createElement('div');
                empty.style.visibility = 'hidden';
                grid.appendChild(empty);
            }

            for (let day = 1; day <= daysInMonth; day++) {
                const dateStr = `${info.year}-${String(info.month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
                const dayData = this.allData[dateStr] || { count: 0, total_time: 0 };

                const cell = document.createElement('div');
                cell.className = 'heat-cell';

                // Keep strings for HTML attributes, but avoid JS parsing them as Date objects
                cell.dataset.date = dateStr;
                cell.dataset.year = info.year;
                cell.dataset.month = info.month;
                cell.dataset.day = day;
                cell.dataset.count = dayData.count;
                cell.dataset.time = dayData.total_time;

                this.applyIntensityClass(cell, dayData.count);
                grid.appendChild(cell);
            }

            monthBlock.appendChild(grid);
            container.appendChild(monthBlock);
        });
    }

    applyIntensityClass(cell, count) {
        cell.classList.remove('level-0', 'level-1', 'level-2', 'level-3', 'level-4');

        if (count > 0) {
            const ratio = count / this.maxOverallSessions;
            let level = 1;
            if (ratio > 0.75) level = 4;
            else if (ratio > 0.5) level = 3;
            else if (ratio > 0.25) level = 2;
            cell.classList.add(`level-${level}`);
        } else {
            cell.classList.add('level-0');
        }
    }

    setupInteractions() {
        const popover = document.getElementById('dayPopover');
        const closeBtn = document.getElementById('closePopover');
        const container = document.getElementById('verticalHeatmap');

        container.addEventListener('click', async (e) => {
            if (e.target.classList.contains('heat-cell')) {
                const dateStr = e.target.dataset.date;
                if (!dateStr) return;

                // Extract exact local integers to bypass UTC offset bugs
                const y = parseInt(e.target.dataset.year);
                const m = parseInt(e.target.dataset.month) - 1; // JS months are 0-indexed
                const d = parseInt(e.target.dataset.day);

                // Build a strict local date object
                const localDateObj = new Date(y, m, d);
                const options = { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' };

                document.getElementById('popoverDate').textContent = localDateObj.toLocaleDateString(undefined, options);
                document.getElementById('popoverCount').textContent = "...";
                document.getElementById('popoverTime').textContent = "...";

                popover.classList.add('active');

                // Fetch fresh data from API
                try {
                    const res = await fetch(`${API_BASE}/sessions/calendar?year=${y}&month=${m + 1}`);
                    if (!res.ok) throw new Error("Network response was not ok");

                    const data = await res.json();
                    const dayData = data.daily_data[dateStr] || { count: 0, total_time: 0 };

                    // Update popover
                    document.getElementById('popoverCount').textContent = dayData.count;
                    document.getElementById('popoverTime').textContent = `${Math.round(dayData.total_time / 60)}m`;

                    // Update cell visuals dynamically if data increased
                    e.target.dataset.count = dayData.count;
                    e.target.dataset.time = dayData.total_time;

                    // Also update our internal dictionary so the streak updates live!
                    this.allData[dateStr] = dayData;
                    this.updateHeroStats();

                    this.applyIntensityClass(e.target, dayData.count);

                } catch (err) {
                    console.error("Failed to fetch live daily data:", err);
                    document.getElementById('popoverCount').textContent = "Err";
                    document.getElementById('popoverTime').textContent = "--";
                }
            }
        });

        closeBtn.addEventListener('click', () => {
            popover.classList.remove('active');
        });

        document.addEventListener('click', (e) => {
            if (!popover.contains(e.target) && !e.target.classList.contains('heat-cell')) {
                popover.classList.remove('active');
            }
        });
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const stats = new SessionStats();
    stats.loadData();
    stats.setupInteractions(); // Called once to prevent event listener stacking

    // Start polling every 30 seconds
    stats.startLiveUpdates(POLLING_INTERVAL);
});