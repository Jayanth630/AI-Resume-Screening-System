(() => {
  const dataElement = document.getElementById("analytics-data");
  if (!dataElement) {
    return;
  }

  const chartData = JSON.parse(dataElement.textContent);
  const statusCanvas = document.getElementById("status-chart");
  const monthlyCanvas = document.getElementById("monthly-chart");
  const [statusEmptyMessage, monthlyEmptyMessage] = document.querySelectorAll(".chart-empty");

  if (typeof Chart === "undefined") {
    [statusEmptyMessage, monthlyEmptyMessage].forEach((message) => {
      message.hidden = false;
      message.textContent = "Charts could not be loaded. Please refresh to try again.";
    });
    console.error("Chart.js did not load; analytics charts could not be rendered.");
    return;
  }

  const statusTotal = chartData.statusValues.reduce((sum, value) => sum + value, 0);
  if (statusTotal > 0) {
    new Chart(statusCanvas, {
      type: "doughnut",
      data: {
        labels: chartData.statusLabels,
        datasets: [{
          data: chartData.statusValues,
          backgroundColor: ["#6e9bd4", "#e7ae5e", "#62b789", "#d77b7b"],
          borderColor: "#fff",
          borderWidth: 4,
          hoverOffset: 7,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: "68%",
        plugins: {
          legend: {
            position: "bottom",
            labels: { usePointStyle: true, pointStyle: "circle", padding: 18 },
          },
        },
      },
    });
  } else {
    statusCanvas.hidden = true;
    statusEmptyMessage.hidden = false;
  }

  const monthlyTotal = chartData.monthlyValues.reduce((sum, value) => sum + value, 0);
  if (monthlyTotal > 0) {
    new Chart(monthlyCanvas, {
      type: "bar",
      data: {
        labels: chartData.monthlyLabels,
        datasets: [{
          label: "Applications",
          data: chartData.monthlyValues,
          backgroundColor: "#42bda9",
          hoverBackgroundColor: "#168d7d",
          borderRadius: 6,
          maxBarThickness: 26,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: {
            grid: { display: false },
            ticks: { color: "#8995a8", maxRotation: 0, autoSkip: true },
          },
          y: {
            beginAtZero: true,
            ticks: { precision: 0, color: "#8995a8" },
            grid: { color: "#edf0f4" },
          },
        },
      },
    });
  } else {
    monthlyCanvas.hidden = true;
    monthlyEmptyMessage.hidden = false;
  }
})();
