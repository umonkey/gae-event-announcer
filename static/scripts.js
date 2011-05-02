$(document).ready(function(){
	$('.sform .check').change(check_boxes);
	$('.sform .text').keyup(check_sbutton);

	// На случай если форма загружена с отмеченными чекбоксами.
	check_boxes();

	// Передаём фокус первому полю формы, если есть.
	$('form input:first').focus();

	$('#showpast').click(function(){
		$('#schedule .past').show();
		// $(this).css('visibility', 'hidden');
		$(this).remove();
	});
});

function check_boxes()
{
	var div_sel = '#' + $(this).attr('name') + '_div';
	$(div_sel).toggleClass('hidden');
	$(div_sel + ' .text').attr('value', '');
	$(div_sel + ' .text').focus();
	check_sbutton();
}

function check_sbutton()
{
	var text = $('#phone_div .text').attr('value')
		+ $('#email_div .text').attr('value');
	$('.sform .button input').attr('disabled', text.length ? '' : 'disabled');
}

function init_carousel(car)
{
	$('#schedule .title').click(function() {
		var item = $(this).parents('tr:first');
		var index = $(this).parents('table:first').find('tr').index(item);
		// Индекс элемента, в который кликнул пользователь — index+1.  Единица
		// не прибавляется чтобы показать соседний элемент, чтобы нужный
		// оказался посередине.
		car.scroll(index);
	});
}
