function createBusRouteKeyboard(routeNumbers, inputField, infoDisplayCallback, prependTo, extraStyles = {}, classes = []) {
	if (inputField !== document.activeElement || document.querySelector(".keyboard-container")) {
		return;
	}

	const main = document.createElement("div");
	main.classList.add("keyboard-main");
	for (let key in extraStyles) {
		main.style[key] = extraStyles[key];
	}
	main.innerHTML = `
		<div class="keyboard-container keyboard-refocus">
			<div class="keyboard-info-box" id="keyboard-info-box-container">
                <p id="keyboard-info-box"></p>
            </div>
		    <div class="keyboard keyboard-refocus">
		        <button class="keyboard-key keyboard-refocus" id="keyboard-1" disabled>1</button>
		        <button class="keyboard-key keyboard-refocus" id="keyboard-2" disabled>2</button>
		        <button class="keyboard-key keyboard-refocus" id="keyboard-3" disabled>3</button>
		        <button class="keyboard-key keyboard-refocus" id="keyboard-4" disabled>4</button>
		        <button class="keyboard-key keyboard-refocus" id="keyboard-5" disabled>5</button>
		        <button class="keyboard-key keyboard-refocus" id="keyboard-6" disabled>6</button>
		        <button class="keyboard-key keyboard-refocus" id="keyboard-7" disabled>7</button>
		        <button class="keyboard-key keyboard-refocus" id="keyboard-8" disabled>8</button>
		        <button class="keyboard-key keyboard-refocus" id="keyboard-9" disabled>9</button>
		        <button class="keyboard-key keyboard-refocus" id="keyboard-Delete"><i class="material-icons">delete</i></button>
	            <button class="keyboard-key keyboard-refocus" id="keyboard-0" disabled>0</button>
	            <button class="keyboard-key keyboard-refocus" id="keyboard-Backspace"><i class="material-icons">backspace</i></button>
		    </div>
		    <div class="keyboard-scrollable-column keyboard-disable-scrollbars keyboard-refocus"></div>
		</div>
	`;

	const handleKeyboardClick = (event, element, key, special = false) => {
		simulateKeyEvent(inputField, key, 'keydown');
		if (!special) {
			inputField.value += key;
		} else if (key == "Delete") {
			inputField.value = "";
		} else if (key == "Backspace") {
			inputField.value = inputField.value.length > 1 ? inputField.value.substring(0, inputField.value.length - 1) : "";
		}
		simulateKeyEvent(inputField, key, 'keyup');
		event.stopPropagation();
		event.preventDefault();
		setTimeout(() => {
			inputField.selectionStart = inputField.selectionEnd = 10000;
		}, 0);
    };

	prependTo.prepend(main);

	const handle = e => {
		let element = e.target;
		if (element.classList.contains("material-icons")) {
			element = element.parentElement;
		}
		if (element.classList.contains("keyboard-key")) {
			let key = element.id.substring("keyboard-".length);
			handleKeyboardClick(event, element, key, key.length > 1);
		}
	};

	document.addEventListener('mousedown', handle);

	let lastValue = null;
	const timerTask = setInterval(() => {
		let currentValue = inputField.value;
		let possibleNextChar = new Set();
		for (let i = 0; i < routeNumbers.length; i++) {
			let routeNumber = routeNumbers[i];
			if (routeNumber.startsWith(currentValue) && routeNumber != currentValue) {
				let nextChar = routeNumber.substring(currentValue.length).substring(0, 1);
				possibleNextChar.add(nextChar);
			}
		}
		for (let i = 0; i <= 9; i++) {
			if (possibleNextChar.has(i.toString())) {
				document.getElementById("keyboard-" + i).disabled = false;
			} else {
				document.getElementById("keyboard-" + i).disabled = true;
			}
		}
		let letterDiv = document.querySelector(".keyboard-scrollable-column");
		let newLetterHtml = "";
		for (let i = 65; i <= 90; i++) {
		    let letter = String.fromCharCode(i);
		    if (possibleNextChar.has(letter)) {
		    	let html = `<button class="keyboard-key keyboard-letter keyboard-refocus" id="keyboard-` + letter + `">` + letter + `</button>`;
		    	newLetterHtml += html;
		    }
		}
		if (letterDiv.innerHTML != newLetterHtml) {
			letterDiv.innerHTML = newLetterHtml;
		}
		if (currentValue !== lastValue) {
			let text = infoDisplayCallback(currentValue);
			let infoBox = document.getElementById("keyboard-info-box");
			infoBox.innerHTML = text;
			lastValue = currentValue;
			if (isElementOverflowing(infoBox)) {
				infoBox.classList.add("marquee");
				document.getElementById("keyboard-info-box-container").style.justifyContent = "left";
			} else {
				infoBox.classList.remove("marquee");
				document.getElementById("keyboard-info-box-container").style.justifyContent = "";
			}
		}
	}, 200);

	const inputHandle = (e) => {
		setTimeout(() => {
			if (inputField !== document.activeElement) {
				main.remove();
				document.removeEventListener('mousedown', handle);
				inputField.removeEventListener('focusout', inputHandle);
				clearInterval(timerTask);
			}
		}, 100);
    };

	inputField.addEventListener('focusout', inputHandle);
}

function simulateKeyEvent(element, keyCode, eventType) {
    let event = new KeyboardEvent(eventType, {
        key: keyCode,
        code: keyCode,
        keyCode: keyCode,
        which: keyCode,
        ctrlKey: false,
        altKey: false,
        shiftKey: false,
        metaKey: false
    });

    element.dispatchEvent(event);
}

function isElementOverflowing(element) {
  	let overflowX = element.offsetWidth > element.parentElement.offsetWidth;
    let overflowY = element.offsetHeight > element.parentElement.offsetHeight;

  	return (overflowX || overflowY);
}