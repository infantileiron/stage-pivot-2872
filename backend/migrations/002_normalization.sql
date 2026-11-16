-- 演出归一：标准演出、别名规则、归一任务、归属与隔离、版本元数据
-- 同时为旧表补列：settlements.updated_at、pivots.normalize_job_id

CREATE TABLE standard_plays (
	id INTEGER NOT NULL AUTO_INCREMENT,
	name VARCHAR(120) NOT NULL,
	note TEXT,
	created VARCHAR(40),
	PRIMARY KEY (id),
	UNIQUE (name)
)

;

CREATE TABLE alias_rules (
	id INTEGER NOT NULL AUTO_INCREMENT,
	alias_name VARCHAR(120) NOT NULL,
	venue VARCHAR(40) NOT NULL,
	start_day VARCHAR(10) NOT NULL,
	end_day VARCHAR(10) NOT NULL,
	target_play_id INTEGER,
	target_rule_id INTEGER,
	state VARCHAR(20),
	note TEXT,
	version INTEGER,
	created VARCHAR(40),
	updated VARCHAR(40),
	PRIMARY KEY (id),
	FOREIGN KEY(target_play_id) REFERENCES standard_plays (id),
	FOREIGN KEY(target_rule_id) REFERENCES alias_rules (id)
)

;

CREATE INDEX ix_alias_lookup ON alias_rules (venue, alias_name)

;

CREATE TABLE normalize_jobs (
	id INTEGER NOT NULL AUTO_INCREMENT,
	name VARCHAR(120),
	kind VARCHAR(20),
	state VARCHAR(20),
	rule_version BIGINT,
	settlement_version BIGINT,
	current_rule_version BIGINT,
	current_settlement_version BIGINT,
	result JSON,
	error TEXT,
	created VARCHAR(40),
	finished VARCHAR(40),
	PRIMARY KEY (id)
)

;

CREATE TABLE play_attributions (
	id INTEGER NOT NULL AUTO_INCREMENT,
	job_id INTEGER NOT NULL,
	settlement_id INTEGER NOT NULL,
	code VARCHAR(60) NOT NULL,
	original_play VARCHAR(120) NOT NULL,
	standard_play_id INTEGER NOT NULL,
	standard_play VARCHAR(120) NOT NULL,
	chain JSON NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_attr_job_settlement UNIQUE (job_id, settlement_id),
	FOREIGN KEY(job_id) REFERENCES normalize_jobs (id),
	FOREIGN KEY(settlement_id) REFERENCES settlements (id),
	FOREIGN KEY(standard_play_id) REFERENCES standard_plays (id)
)

;

CREATE TABLE play_isolations (
	id INTEGER NOT NULL AUTO_INCREMENT,
	job_id INTEGER NOT NULL,
	settlement_id INTEGER NOT NULL,
	code VARCHAR(60) NOT NULL,
	original_play VARCHAR(120) NOT NULL,
	venue VARCHAR(40),
	day VARCHAR(10),
	reason VARCHAR(30) NOT NULL,
	detail TEXT,
	gross_cents BIGINT,
	refund_cents BIGINT,
	fee_cents BIGINT,
	net_cents BIGINT,
	PRIMARY KEY (id),
	CONSTRAINT uq_iso_job_settlement UNIQUE (job_id, settlement_id),
	FOREIGN KEY(job_id) REFERENCES normalize_jobs (id),
	FOREIGN KEY(settlement_id) REFERENCES settlements (id)
)

;

CREATE TABLE meta_kv (
	id INTEGER NOT NULL AUTO_INCREMENT,
	`key` VARCHAR(60) NOT NULL,
	value VARCHAR(120),
	PRIMARY KEY (id),
	UNIQUE (`key`)
)

;

ALTER TABLE settlements ADD COLUMN updated_at VARCHAR(40)

;

ALTER TABLE pivots ADD COLUMN normalize_job_id INTEGER

;
