document.addEventListener('DOMContentLoaded',()=>{
  document.querySelectorAll('[data-confirm]').forEach(button=>button.addEventListener('click',event=>{if(!confirm(button.dataset.confirm))event.preventDefault()}));
  if(window.location.pathname!== '/utilities') return;
  document.querySelectorAll('form').forEach(form=>{
    const room=form.querySelector('[name="room_id"]'); const recordMonth=form.querySelector('[name="reading_month"]');
    const oldElectricity=form.querySelector('[name="old_electricity"]'); const oldWater=form.querySelector('[name="old_water"]');
    if(!room || !recordMonth || !oldElectricity || !oldWater) return;
    let notice=form.querySelector('.utility-inheritance');
    if(!notice){notice=document.createElement('small');notice.className='utility-inheritance text-muted d-block';oldWater.closest('.col-6, .col-12')?.after(notice);}
    const inherit=async()=>{
      if(!room.value || !recordMonth.value) return;
      notice.textContent='Đang kiểm tra chỉ số tháng trước...';
      try{
        const response=await fetch(`/utilities/previous?room_id=${encodeURIComponent(room.value)}&month=${encodeURIComponent(recordMonth.value)}`);
        const data=await response.json();
        if(data.found){oldElectricity.value=data.old_electricity;oldWater.value=data.old_water;notice.textContent=`Đã kế thừa chỉ số mới của tháng ${data.month} làm chỉ số cũ.`;}
        else notice.textContent='Chưa có chỉ số tháng trước. Hãy nhập chỉ số cũ thủ công.';
      }catch{notice.textContent='Không thể kiểm tra chỉ số tháng trước.';}
    };
    room.addEventListener('change',inherit);recordMonth.addEventListener('change',inherit);
    inherit();
  });
});
