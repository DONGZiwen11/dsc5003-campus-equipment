UPDATE student SET name = CASE id WHEN 'S001' THEN 'Alex Chen' WHEN 'S002' THEN 'Jamie Lin' ELSE 'Morgan Chow' END WHERE (id,name) IN (('S001','陈晓'),('S002','林雨'),('S003','周明'));
UPDATE model SET category = 'Photography', name = 'Portable Camera' WHERE id=1 AND category='影像' AND name='便携相机';
UPDATE model SET category = 'Photography', name = 'Tripod' WHERE id=2 AND category='影像' AND name='三脚架';
UPDATE model SET category = 'Computing', name = 'Lab Laptop' WHERE id=3 AND category='计算' AND name='实验室笔记本';
UPDATE model SET category = 'Presentation', name = 'Portable Projector' WHERE id=4 AND category='演示' AND name='便携投影仪';