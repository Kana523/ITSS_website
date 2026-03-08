const trigger = document.getElementById('ccp-legal-trigger');
        const tooltip = document.getElementById('ccp-legal-tooltip');

        // Show + position near pointer on hover / mousemove
        trigger.addEventListener('mousemove', (e) => {
        // show first so we can measure its size
        tooltip.style.display = 'block';

        const rect = tooltip.getBoundingClientRect();

        const padding = 10;
        let left = e.clientX - rect.width / 2;
        let top  = e.clientY - rect.height - 15;

        // clamp horizontally
        left = Math.max(padding, Math.min(left, window.innerWidth - rect.width - padding));

        // if it goes off the top, put it below instead
        if (top < padding) {
            top = e.clientY + 15;
        }

        tooltip.style.left = `${left}px`;
        tooltip.style.top  = `${top}px`;

        });

        trigger.addEventListener('mouseleave', () => {
          tooltip.style.display = 'none';
        });

        // Click toggle (useful for touch devices)
        trigger.addEventListener('click', (e) => {
        e.preventDefault();
          const isVisible = tooltip.style.display === 'block';
          if (isVisible) {
            tooltip.style.display = 'none';
          } else {
            // put it somewhere sensible if no mousemove yet
            tooltip.style.display = 'block';
            tooltip.style.left = `${window.innerWidth / 2 - 150}px`;
            tooltip.style.top = `${window.innerHeight / 2 - 80}px`;
          }
        });

        // Optional: hide tooltip on any click outside
        document.addEventListener('click', (e) => {
          if (!trigger.contains(e.target) && !tooltip.contains(e.target)) {
            tooltip.style.display = 'none';
          }
});