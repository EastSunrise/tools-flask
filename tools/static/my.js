(function () {
    $('.filter').on('change', function () {
        $('#form').submit();
    });

    let _order_by = $('#order_by');
    let _desc = $('#desc');
    let src_order_by = _order_by.val();
    let src_desc = _desc.val();
    $('.sortable').each(function () {
        $(this).attr('title', '点击排序');
        let order_by = $(this).attr('id');
        if (order_by === src_order_by) {
            $(this).children('span.arrow').attr('class', 'arrow ' + src_desc);
            $(this).on('click', function () {
                _desc.val(src_desc.toLowerCase() === 'desc' ? 'asc' : 'desc');
                $('#form').submit();
            });
        } else {
            $(this).children('span.arrow').attr('class', 'arrow');
            $(this).on('click', function () {
                _order_by.val(order_by);
                _desc.val('asc');
                $('#form').submit();
            });
        }
    });

    $('.playBtn').each(function () {
        updateArchived($(this), $(this).data('archived'), $(this).data('id'));
    })
})();


function updateArchived(_this, archived, subject_id) {
    let playBtn = $(_this);
    let func;
    if (archived === 'added') {
        playBtn.attr('title', '点击搜索');
        func = function () {
            getJSON(_this, 'http://localhost:5000/video/collect?id=' + subject_id, '正在搜索', function (result) {
                updateArchived(_this, result['archived'], subject_id);
            });
        };
    } else if (archived === 'playable') {
        playBtn.attr('title', '点击播放');
        func = function () {
            getJSON(_this, 'http://localhost:5000/video/play?id=' + subject_id, '正在启动', function (result) {
                if (!result.success) {
                    alert('无法播放');
                }
                updateArchived(_this, archived, subject_id);
            })
        };
    } else if (archived === 'idm' || archived === 'downloading') {
        playBtn.attr('title', '点击归档');
        func = function () {
            let yOrN = confirm('全部下载完成？');
            if (yOrN) {
                getJSON(_this, 'http://localhost:5000/video/temp?id=' + subject_id, '正在归档', function (result) {
                    let a = result['archived'];
                    if (a === -2) {
                        alert('I/O错误');
                        updateArchived(_this, archived, subject_id);
                    } else {
                        updateArchived(_this, a, subject_id);
                    }
                })
            }
        };
    } else {
        playBtn.parent().prepend('<span>找不到资源！</span>');
        playBtn.remove();
    }
    if (func) {
        playBtn.off('click').on('click', null, null, func);
    }
}

function getJSON(_this, url, tip, callback) {
    $(_this).attr('hidden', true);
    let clickTip = $(_this).prev();
    clickTip.text(tip);
    clickTip.attr('hidden', false);
    let spotCount = 0;
    let timer = setInterval(function () {
        let text = tip + '.';
        for (let i = 0; i < spotCount; i++) {
            text += '.';
        }
        clickTip.text(text);
        if (spotCount === 2) {
            spotCount = 0;
        } else {
            spotCount++;
        }
    }, 500);
    $.ajax(url, {
        type: 'get',
        dataType: 'json',
        success: function (result) {
            callback(result);
            clickTip.attr('hidden', true);
        },
        error: function () {
            clickTip.text('无法连接到服务器！');
        },
        complete: function () {
            $(_this).attr('hidden', false);
            clearInterval(timer);
        }
    });
}