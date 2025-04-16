/**
 * Searchable Select dropdown enhancement
 * Makes select elements with class 'searchable-select' searchable
 */
function initializeSearchableSelects() {
    const searchableSelects = document.querySelectorAll('select.searchable-select');
    
    searchableSelects.forEach(select => {
        // Create a wrapper div
        const wrapper = document.createElement('div');
        wrapper.className = 'searchable-select-container';
        select.parentNode.insertBefore(wrapper, select);
        wrapper.appendChild(select);
        
        // Create search input
        const searchInput = document.createElement('input');
        searchInput.type = 'text';
        searchInput.className = 'searchable-select-input';
        searchInput.placeholder = 'Search...';
        wrapper.insertBefore(searchInput, select);
        
        // Handle input events on search box
        searchInput.addEventListener('input', function() {
            const searchText = this.value.toLowerCase();
            const options = select.querySelectorAll('option');
            
            options.forEach(option => {
                // Skip the first "Select..." option
                if (option.value === '') return;
                
                const optionText = option.textContent.toLowerCase();
                if (optionText.includes(searchText)) {
                    option.style.display = '';
                } else {
                    option.style.display = 'none';
                }
            });
        });
        
        // Style the select container
        wrapper.style.position = 'relative';
        searchInput.style.width = '100%';
        searchInput.style.marginBottom = '5px';
        searchInput.style.padding = '8px';
        searchInput.style.boxSizing = 'border-box';
    });
}

// Initialize when the DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    initializeSearchableSelects();
});
