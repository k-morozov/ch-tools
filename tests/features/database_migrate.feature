Feature: chadmin database migrate command

  Background:
    Given default configuration
    And a working s3
    And a working zookeeper
    And a working clickhouse on clickhouse01
    And a working clickhouse on clickhouse02
    
  @require_version_24.8
  Scenario: Migrate empty database in host
    When we execute query on clickhouse01
    """
    CREATE DATABASE non_repl_db;
    """
    And we execute command on clickhouse01
    """
    chadmin database migrate -d non_repl_db 
    """
    When we execute query on clickhouse01
    """
    SELECT engine FROM system.databases WHERE database='non_repl_db'
    """
    Then we get response
    """
    Replicated
    """
    When we execute query on clickhouse01
    """
    CREATE TABLE non_repl_db.bar2
    (
        `a` Int
    )
    ENGINE = MergeTree
    ORDER BY a
    """
    When we execute query on clickhouse01
    """
        SELECT name FROM system.tables WHERE database='non_repl_db'
    """
    Then we get response
    """
    bar2
    """

  @require_version_24.8
  Scenario: Migrate non exists database
    When we try to execute command on clickhouse01
    """
    chadmin database migrate -d non_exists_db 
    """
    Then it fails with response contains
    """
    Database non_exists_db does not exists, skip migrating
    """

  @require_version_24.8
  Scenario Outline: Migrate database with different tables in host created by hosts
    When we execute query on clickhouse01
    """
    CREATE DATABASE non_repl_db;
    """
    When we execute query on clickhouse01
    """
    CREATE TABLE non_repl_db.foo
    (
        `a` Int
    )
    ENGINE = <table_engine>
    ORDER BY a
    """
    And we execute query on clickhouse01
    """
    INSERT INTO non_repl_db.foo VALUES (42)
    """

    And we execute command on clickhouse01
    """
    chadmin database migrate -d non_repl_db 
    """
    When we execute query on clickhouse01
    """
    SELECT engine FROM system.databases WHERE database='non_repl_db'
    """
    Then we get response
    """
    Replicated
    """
    When we execute query on clickhouse01
    """
    ALTER TABLE non_repl_db.foo ADD COLUMN b String DEFAULT 'value'
    """
    When we execute query on clickhouse01
    """
    SELECT * FROM non_repl_db.foo FORMAT Values
    """
    Then we get response
    """
    (42,'value')
    """
  Examples:
    | table_engine                                                 |
    | MergeTree                                                    |
    | ReplicatedMergeTree('/clickhouse/foo', '{replica}')          |

  @require_version_24.8
  Scenario Outline: Migrate database with different tables in host created on cluster
    When we execute query on clickhouse01
    """
    CREATE DATABASE non_repl_db;
    """
    When we execute query on clickhouse01
    """
    CREATE TABLE non_repl_db.foo
    ON CLUSTER '{cluster}'
    (
        `a` Int
    )
    ENGINE = <table_engine>
    ORDER BY a
    """
    And we execute query on clickhouse01
    """
    INSERT INTO non_repl_db.foo VALUES (42)
    """

    And we execute command on clickhouse01
    """
    chadmin database migrate -d non_repl_db 
    """
    When we execute query on clickhouse01
    """
    SELECT engine FROM system.databases WHERE database='non_repl_db'
    """
    Then we get response
    """
    Replicated
    """
    When we execute query on clickhouse01
    """
    ALTER TABLE non_repl_db.foo ADD COLUMN b String DEFAULT 'value'
    """
    When we execute query on clickhouse01
    """
    SELECT * FROM non_repl_db.foo FORMAT Values
    """
    Then we get response
    """
    (42,'value')
    """
  Examples:
    | table_engine                                                 |
    | MergeTree                                                    |
    | ReplicatedMergeTree('/clickhouse/foo', '{replica}')          |

  @require_version_24.8
  Scenario: Migrate empty database in cluster
    When we execute query on clickhouse01
    """
    CREATE DATABASE non_repl_db ON CLUSTER '{cluster}';
    """
    And we execute command on clickhouse01
    """
    chadmin database migrate -d non_repl_db 
    """
   
    When we execute query on clickhouse01
    """
    SELECT engine FROM system.databases WHERE database='non_repl_db'
    """
    Then we get response
    """
    Replicated
    """
    When we execute command on clickhouse02
    """
    chadmin database migrate -d non_repl_db 
    """

    When we execute command on clickhouse01
    """
    supervisorctl restart clickhouse-server
    """

    When we execute command on clickhouse02
    """
    supervisorctl restart clickhouse-server
    """
    When we sleep for 10 seconds
    
    And we execute query on clickhouse02
    """
    SELECT engine FROM system.databases WHERE database='non_repl_db'
    """
    Then we get response
    """
    Replicated
    """

    When we execute query on clickhouse01
    """
    CREATE TABLE non_repl_db.bar2
    (
        `a` Int
    )
    ENGINE = MergeTree
    ORDER BY a
    """
    When we execute query on clickhouse01
    """
        SELECT name FROM system.tables WHERE database='non_repl_db'
    """
    Then we get response
    """
    bar2
    """
    When we execute query on clickhouse02
    """
    SELECT name FROM system.tables WHERE database='non_repl_db'
    """
    Then we get response
    """
    bar2
    """

  @require_version_24.8
  Scenario: Migrate database with MergeTree table by hosts
    When we execute query on clickhouse01
    """
    CREATE DATABASE non_repl_db ON CLUSTER '{cluster}';
    """
    When we execute query on clickhouse01
    """
    CREATE TABLE non_repl_db.foo
    (
        `a` Int
    )
    ENGINE = MergeTree
    ORDER BY a
    """
    And we execute query on clickhouse01
    """
    INSERT INTO non_repl_db.foo VALUES (42)
    """
    And we execute query on clickhouse02
    """
    CREATE TABLE non_repl_db.foo
    (
        `a` Int
    )
    ENGINE = MergeTree
    ORDER BY a
    """
    And we execute query on clickhouse02
    """
    INSERT INTO non_repl_db.foo VALUES (42)
    """
    And we execute command on clickhouse01
    """
    chadmin database migrate -d non_repl_db 
    """
    When we execute query on clickhouse01
    """
    SELECT name FROM system.databases ORDER BY name FORMAT Values
    """
    Then we get response
    """
    ('INFORMATION_SCHEMA'),('default'),('information_schema'),('non_repl_db'),('system')
    """
    When we execute query on clickhouse01
    """
    SELECT engine FROM system.databases WHERE database='non_repl_db'
    """
    Then we get response
    """
    Replicated
    """
    When we execute query on clickhouse01
    """
    SELECT * FROM non_repl_db.foo FORMAT Values
    """
    Then we get response
    """
    (42)
    """

    When we execute command on clickhouse02
    """
    chadmin database migrate -d non_repl_db 
    """
    When we execute command on clickhouse02
    """
    supervisorctl restart clickhouse-server
    """
    When we sleep for 10 seconds

    When we execute query on clickhouse02
    """
    SELECT name FROM system.databases ORDER BY name FORMAT Values
    """
    Then we get response
    """
    ('INFORMATION_SCHEMA'),('default'),('information_schema'),('non_repl_db'),('system')
    """
    When we execute query on clickhouse02
    """
    SELECT engine FROM system.databases WHERE database='non_repl_db'
    """
    Then we get response
    """
    Replicated
    """
    When we execute query on clickhouse02
    """
    SELECT * FROM non_repl_db.foo FORMAT Values
    """
    Then we get response
    """
    (42)
    """

    When we execute query on clickhouse01
    """
    ALTER TABLE non_repl_db.foo ADD COLUMN b String DEFAULT 'value'
    """

    When we execute query on clickhouse01
    """
    SELECT * FROM non_repl_db.foo FORMAT Values
    """
    Then we get response
    """
    (42,'value')
    """
    When we execute query on clickhouse02
    """
    SELECT * FROM non_repl_db.foo FORMAT Values
    """
    Then we get response
    """
    (42,'value')
    """

  @require_version_24.8
  Scenario: Migrate database with ReplicatedMergeTree table with stopped first replica
    When we execute query on clickhouse01
    """
    CREATE DATABASE non_repl_db ON CLUSTER '{cluster}';
    """
    When we execute query on clickhouse01
    """
    CREATE TABLE non_repl_db.foo
    (
        `a` Int
    )
    ENGINE = ReplicatedMergeTree('/clickhouse/foo', '{replica}')
    ORDER BY a
    """
    And we execute query on clickhouse02
    """
    CREATE TABLE non_repl_db.foo
    (
        `a` Int
    )
    ENGINE = ReplicatedMergeTree('/clickhouse/foo', '{replica}')
    ORDER BY a
    """
    And we execute query on clickhouse01
    """
    INSERT INTO non_repl_db.foo VALUES (42)
    """
    And we execute command on clickhouse01
    """
    chadmin database migrate -d non_repl_db 
    """
    Then it completes successfully

    When we execute command on clickhouse01
    """
    supervisorctl stop clickhouse-server
    """

    When we execute command on clickhouse02
    """
    chadmin database migrate -d non_repl_db 
    """
    Then it completes successfully

    When we execute command on clickhouse02
    """
    supervisorctl restart clickhouse-server
    """
    When we sleep for 10 seconds

    When we execute query on clickhouse02
    """
    SELECT engine FROM system.databases WHERE database='non_repl_db'
    """
    Then we get response
    """
    Replicated
    """

    When we execute query on clickhouse02
    """
    SELECT * FROM non_repl_db.foo FORMAT Values
    """
    Then we get response
    """
    (42)
    """

  @require_version_24.8
  Scenario Outline: Migrate database with ReplicatedMergeTree table createed by hosts
    When we execute query on clickhouse01
    """
    CREATE DATABASE non_repl_db ON CLUSTER '{cluster}';
    """
    When we execute query on clickhouse01
    """
    CREATE TABLE non_repl_db.foo
    (
        `a` Int
    )
    ENGINE = <table_engine>
    ORDER BY a
    """
    And we execute query on clickhouse02
    """
    CREATE TABLE non_repl_db.foo
    (
        `a` Int
    )
    ENGINE = <table_engine>
    ORDER BY a
    """
    And we execute query on clickhouse01
    """
    INSERT INTO non_repl_db.foo VALUES (42)
    """
    And we execute command on clickhouse01
    """
    chadmin database migrate -d non_repl_db 
    """
    When we execute query on clickhouse01
    """
    SELECT name FROM system.databases ORDER BY name FORMAT Values
    """
    Then we get response
    """
    ('INFORMATION_SCHEMA'),('default'),('information_schema'),('non_repl_db'),('system')
    """
    When we execute query on clickhouse01
    """
    SELECT engine FROM system.databases WHERE database='non_repl_db'
    """
    Then we get response
    """
    Replicated
    """
    When we execute query on clickhouse01
    """
    SELECT * FROM non_repl_db.foo FORMAT Values
    """
    Then we get response
    """
    (42)
    """

    When we execute command on clickhouse02
    """
    chadmin database migrate -d non_repl_db 
    """
    When we execute command on clickhouse02
    """
    supervisorctl restart clickhouse-server
    """
    When we sleep for 10 seconds

    When we execute query on clickhouse02
    """
    SELECT name FROM system.databases ORDER BY name FORMAT Values
    """
    Then we get response
    """
    ('INFORMATION_SCHEMA'),('default'),('information_schema'),('non_repl_db'),('system')
    """
    When we execute query on clickhouse02
    """
    SELECT engine FROM system.databases WHERE database='non_repl_db'
    """
    Then we get response
    """
    Replicated
    """
    When we execute query on clickhouse02
    """
    SELECT * FROM non_repl_db.foo FORMAT Values
    """
    Then we get response
    """
    (42)
    """

    When we execute query on clickhouse02
    """
    SELECT zookeeper_path FROM system.replicas WHERE table='foo' FORMAT Values
    """
    Then we get response
    """
    ('<zookeeper_path>')
    """

    When we execute query on clickhouse01
    """
    ALTER TABLE non_repl_db.foo ADD COLUMN b String DEFAULT 'value'
    """

    When we execute query on clickhouse01
    """
    SELECT * FROM non_repl_db.foo FORMAT Values
    """
    Then we get response
    """
    (42,'value')
    """
    When we execute query on clickhouse02
    """
    SELECT * FROM non_repl_db.foo FORMAT Values
    """
    Then we get response
    """
    (42,'value')
    """
    When we execute query on clickhouse01
    """
    INSERT INTO non_repl_db.foo VALUES (43, 'value2')
    """
    When we execute query on clickhouse02
    """
    SYSTEM SYNC REPLICA non_repl_db.foo
    """
    When we execute query on clickhouse01
    """
    SELECT * FROM non_repl_db.foo ORDER BY a FORMAT Values
    """
    Then we get response
    """
    (42,'value'),(43,'value2')
    """
    When we execute query on clickhouse02
    """
    SELECT * FROM non_repl_db.foo ORDER BY a FORMAT Values
    """
    Then we get response
    """
    (42,'value'),(43,'value2')
    """
    When we execute query on clickhouse01
    """
    DROP DATABASE non_repl_db ON CLUSTER '{cluster}';
    """
  Examples:
      | table_engine                                                 | zookeeper_path          |
      | ReplicatedMergeTree('/clickhouse/foo/{shard}', '{replica}')  | /clickhouse/foo/shard1  |
      | ReplicatedMergeTree('/clickhouse/foo', '{replica}')          | /clickhouse/foo         |


  @require_version_24.8
  Scenario Outline: Migrate database with ReplicatedMergeTree table created on cluster
    When we execute query on clickhouse01
    """
    CREATE DATABASE non_repl_db ON CLUSTER '{cluster}';
    """
    When we execute query on clickhouse01
    """
    CREATE TABLE non_repl_db.foo
    ON CLUSTER '{cluster}'
    (
        `a` Int
    )
    ENGINE = <table_engine>
    ORDER BY a
    """
    And we execute query on clickhouse01
    """
    INSERT INTO non_repl_db.foo VALUES (42)
    """
    And we execute command on clickhouse01
    """
    chadmin database migrate -d non_repl_db 
    """
    When we execute query on clickhouse01
    """
    SELECT name FROM system.databases ORDER BY name FORMAT Values
    """
    Then we get response
    """
    ('INFORMATION_SCHEMA'),('default'),('information_schema'),('non_repl_db'),('system')
    """
    When we execute query on clickhouse01
    """
    SELECT engine FROM system.databases WHERE database='non_repl_db'
    """
    Then we get response
    """
    Replicated
    """
    When we execute query on clickhouse01
    """
    SELECT * FROM non_repl_db.foo FORMAT Values
    """
    Then we get response
    """
    (42)
    """

    When we execute command on clickhouse02
    """
    chadmin database migrate -d non_repl_db 
    """

    When we execute query on clickhouse02
    """
    SELECT name FROM system.databases ORDER BY name FORMAT Values
    """
    Then we get response
    """
    ('INFORMATION_SCHEMA'),('default'),('information_schema'),('non_repl_db'),('system')
    """
    When we execute query on clickhouse02
    """
    SELECT engine FROM system.databases WHERE database='non_repl_db'
    """
    Then we get response
    """
    Replicated
    """
    When we execute query on clickhouse02
    """
    SELECT * FROM non_repl_db.foo FORMAT Values
    """
    Then we get response
    """
    (42)
    """

    When we execute query on clickhouse02
    """
    SELECT zookeeper_path FROM system.replicas WHERE table='foo' FORMAT Values
    """
    Then we get response
    """
    ('<zookeeper_path>')
    """

    When we execute query on clickhouse01
    """
    ALTER TABLE non_repl_db.foo ADD COLUMN b String DEFAULT 'value'
    """

    When we execute query on clickhouse01
    """
    SELECT * FROM non_repl_db.foo FORMAT Values
    """
    Then we get response
    """
    (42,'value')
    """
    When we execute query on clickhouse02
    """
    SELECT * FROM non_repl_db.foo FORMAT Values
    """
    Then we get response
    """
    (42,'value')
    """
    When we execute query on clickhouse01
    """
    INSERT INTO non_repl_db.foo VALUES (43, 'value2')
    """
    When we execute query on clickhouse02
    """
    SYSTEM SYNC REPLICA non_repl_db.foo
    """
    When we execute query on clickhouse01
    """
    SELECT * FROM non_repl_db.foo ORDER BY a FORMAT Values
    """
    Then we get response
    """
    (42,'value'),(43,'value2')
    """
    When we execute query on clickhouse02
    """
    SELECT * FROM non_repl_db.foo ORDER BY a FORMAT Values
    """
    Then we get response
    """
    (42,'value'),(43,'value2')
    """
    When we execute query on clickhouse01
    """
    DROP DATABASE non_repl_db ON CLUSTER '{cluster}';
    """
  Examples:
      | table_engine                                                 | zookeeper_path          |
      | ReplicatedMergeTree('/clickhouse/foo/{shard}', '{replica}')  | /clickhouse/foo/shard1  |
      | ReplicatedMergeTree('/clickhouse/foo', '{replica}')          | /clickhouse/foo         |

  @require_version_24.8
  Scenario: Migrate database with Distributed table created by hosts
    When we execute query on clickhouse01
    """
    CREATE DATABASE non_repl_db ON CLUSTER '{cluster}';
    """
    When we execute query on clickhouse01
    """
    CREATE TABLE non_repl_db.foo
    (
        `a` Int
    )
    ENGINE = ReplicatedMergeTree('/clickhouse/foo', '{replica}')
    ORDER BY a
    """
    When we execute query on clickhouse01
    """
    CREATE TABLE non_repl_db.dist_foo
    AS non_repl_db.foo
    ENGINE = Distributed('{cluster}', 'non_repl_db', 'foo', a);
    """
    When we execute query on clickhouse02
    """
    CREATE TABLE non_repl_db.foo
    (
        `a` Int
    )
    ENGINE = ReplicatedMergeTree('/clickhouse/foo', '{replica}')
    ORDER BY a
    """
    When we execute query on clickhouse02
    """
    CREATE TABLE non_repl_db.dist_foo
    AS non_repl_db.foo
    ENGINE = Distributed('{cluster}', 'non_repl_db', 'foo', a);
    """
    And we execute query on clickhouse01
    """
    INSERT INTO non_repl_db.dist_foo VALUES (42)
    """
    And we execute command on clickhouse01
    """
    chadmin database migrate -d non_repl_db 
    """
    When we execute query on clickhouse01
    """
    SELECT name FROM system.databases ORDER BY name FORMAT Values
    """
    Then we get response
    """
    ('INFORMATION_SCHEMA'),('default'),('information_schema'),('non_repl_db'),('system')
    """
    When we execute query on clickhouse01
    """
    SELECT engine FROM system.databases WHERE database='non_repl_db'
    """
    Then we get response
    """
    Replicated
    """
    When we execute query on clickhouse01
    """
    SELECT * FROM non_repl_db.dist_foo FORMAT Values
    """
    Then we get response
    """
    (42)
    """

    When we execute command on clickhouse02
    """
    chadmin database migrate -d non_repl_db 
    """
    When we execute command on clickhouse02
    """
    supervisorctl restart clickhouse-server
    """
    When we sleep for 10 seconds

    When we execute query on clickhouse02
    """
    SELECT name FROM system.databases ORDER BY name FORMAT Values
    """
    Then we get response
    """
    ('INFORMATION_SCHEMA'),('default'),('information_schema'),('non_repl_db'),('system')
    """
    When we execute query on clickhouse02
    """
    SELECT engine FROM system.databases WHERE database='non_repl_db'
    """
    Then we get response
    """
    Replicated
    """
    When we execute query on clickhouse02
    """
    SELECT * FROM non_repl_db.dist_foo FORMAT Values
    """
    Then we get response
    """
    (42)
    """

  @require_version_24.8
  Scenario: Migrate database with Distributed table created on cluster
    When we execute query on clickhouse01
    """
    CREATE DATABASE non_repl_db ON CLUSTER '{cluster}';
    """
    When we execute query on clickhouse01
    """
    CREATE TABLE non_repl_db.foo
    ON CLUSTER '{cluster}'
    (
        `a` Int
    )
    ENGINE = ReplicatedMergeTree('/clickhouse/foo', '{replica}')
    ORDER BY a
    """
    When we execute query on clickhouse01
    """
    CREATE TABLE non_repl_db.dist_foo
    ON CLUSTER '{cluster}'
    AS non_repl_db.foo
    ENGINE = Distributed('{cluster}', 'non_repl_db', 'foo', a);
    """
    And we execute query on clickhouse01
    """
    INSERT INTO non_repl_db.dist_foo VALUES (42)
    """
    And we execute command on clickhouse01
    """
    chadmin database migrate -d non_repl_db 
    """
    When we execute query on clickhouse01
    """
    SELECT name FROM system.databases ORDER BY name FORMAT Values
    """
    Then we get response
    """
    ('INFORMATION_SCHEMA'),('default'),('information_schema'),('non_repl_db'),('system')
    """
    When we execute query on clickhouse01
    """
    SELECT engine FROM system.databases WHERE database='non_repl_db'
    """
    Then we get response
    """
    Replicated
    """
    When we execute query on clickhouse01
    """
    SELECT * FROM non_repl_db.dist_foo FORMAT Values
    """
    Then we get response
    """
    (42)
    """

    When we execute command on clickhouse02
    """
    chadmin database migrate -d non_repl_db 
    """

    When we execute query on clickhouse02
    """
    SELECT name FROM system.databases ORDER BY name FORMAT Values
    """
    Then we get response
    """
    ('INFORMATION_SCHEMA'),('default'),('information_schema'),('non_repl_db'),('system')
    """
    When we execute query on clickhouse02
    """
    SELECT engine FROM system.databases WHERE database='non_repl_db'
    """
    Then we get response
    """
    Replicated
    """
    When we execute query on clickhouse02
    """
    SELECT * FROM non_repl_db.dist_foo FORMAT Values
    """
    Then we get response
    """
    (42)
    """

  @require_version_24.8
  Scenario: Migrate database with MATERIALIZED VIEW by host
    When we execute query on clickhouse01
    """
    CREATE DATABASE non_repl_db ON CLUSTER '{cluster}';
    """
    When we execute query on clickhouse01
    """
    CREATE TABLE non_repl_db.foo
    (
        `a` Int
    )
    ENGINE = MergeTree
    ORDER BY a
    """
    And we execute query on clickhouse01
    """
    INSERT INTO non_repl_db.foo VALUES (42)
    """
    And we execute query on clickhouse01
    """
    CREATE MATERIALIZED VIEW non_repl_db.foo_mw TO non_repl_db.foo AS SELECT * FROM non_repl_db.foo
    """
    And we execute command on clickhouse01
    """
    chadmin database migrate -d non_repl_db 
    """
    When we execute query on clickhouse01
    """
    SELECT name FROM system.databases ORDER BY name FORMAT Values
    """
    Then we get response
    """
    ('INFORMATION_SCHEMA'),('default'),('information_schema'),('non_repl_db'),('system')
    """
    When we execute query on clickhouse01
    """
    SELECT engine FROM system.databases WHERE database='non_repl_db'
    """
    Then we get response
    """
    Replicated
    """
    When we execute query on clickhouse01
    """
    SELECT * FROM non_repl_db.foo_mw FORMAT Values
    """
    Then we get response
    """
    (42)
    """

  @require_version_24.8
  Scenario: Migrate database with MATERIALIZED VIEW by cluster
    When we execute query on clickhouse01
    """
    CREATE DATABASE non_repl_db ON CLUSTER '{cluster}';
    """
    When we execute query on clickhouse01
    """
    CREATE TABLE non_repl_db.foo
    ON CLUSTER '{cluster}'
    (
        `a` Int
    )
    ENGINE = MergeTree
    ORDER BY a
    """
    And we execute query on clickhouse01
    """
    INSERT INTO non_repl_db.foo VALUES (42)
    """
    And we execute query on clickhouse02
    """
    INSERT INTO non_repl_db.foo VALUES (43)
    """
    And we execute query on clickhouse01
    """
    CREATE MATERIALIZED VIEW non_repl_db.foo_mw
    ON CLUSTER '{cluster}'
    TO non_repl_db.foo AS SELECT * FROM non_repl_db.foo
    """
    When we execute command on clickhouse01
    """
    chadmin database migrate -d non_repl_db 
    """
    When we execute query on clickhouse01
    """
    SELECT name FROM system.databases ORDER BY name FORMAT Values
    """
    Then we get response
    """
    ('INFORMATION_SCHEMA'),('default'),('information_schema'),('non_repl_db'),('system')
    """
    When we execute query on clickhouse01
    """
    SELECT engine FROM system.databases WHERE database='non_repl_db'
    """
    Then we get response
    """
    Replicated
    """
    When we execute query on clickhouse01
    """
    SELECT * FROM non_repl_db.foo_mw FORMAT Values
    """
    Then we get response
    """
    (42)
    """
    When we execute command on clickhouse02
    """
    chadmin database migrate -d non_repl_db 
    """

    When we execute query on clickhouse02
    """
    SELECT name FROM system.databases ORDER BY name FORMAT Values
    """
    Then we get response
    """
    ('INFORMATION_SCHEMA'),('default'),('information_schema'),('non_repl_db'),('system')
    """
    When we execute query on clickhouse02
    """
    SELECT engine FROM system.databases WHERE database='non_repl_db'
    """
    Then we get response
    """
    Replicated
    """
    When we execute query on clickhouse02
    """
    SELECT * FROM non_repl_db.foo FORMAT Values
    """
    Then we get response
    """
    (43)
    """
    When we execute query on clickhouse02
    """
    SELECT * FROM non_repl_db.foo_mw FORMAT Values
    """
    Then we get response
    """
    (43)
    """

  @require_version_24.8
  Scenario: Migrate database with ReplicatedMergeTree before update schema in another replica
    When we execute query on clickhouse01
    """
    CREATE DATABASE non_repl_db ON CLUSTER '{cluster}';
    """
    When we execute query on clickhouse01
    """
    CREATE TABLE non_repl_db.foo
    ON CLUSTER '{cluster}'
    (
        `a` Int
    )
    ENGINE = ReplicatedMergeTree('/clickhouse/foo', '{replica}')
    ORDER BY a
    """
    And we execute query on clickhouse01
    """
    INSERT INTO non_repl_db.foo VALUES (42)
    """
    And we execute command on clickhouse01
    """
    chadmin database migrate -d non_repl_db 
    """
    When we execute query on clickhouse02
    """
    ALTER TABLE non_repl_db.foo ADD COLUMN b String DEFAULT 'value'
    """

    When we execute command on clickhouse02
    """
    chadmin database migrate -d non_repl_db 
    """
    When we execute query on clickhouse01
    """
    SELECT * FROM non_repl_db.foo FORMAT Values
    """
    Then we get response
    """
    (42,'value')
    """
    When we execute query on clickhouse02
    """
    SELECT * FROM non_repl_db.foo FORMAT Values
    """
    Then we get response
    """
    (42,'value')
    """

  @require_version_24.8
  Scenario: Migrate database with MergeTree before update schema in another replica
    When we execute query on clickhouse01
    """
    CREATE DATABASE non_repl_db ON CLUSTER '{cluster}';
    """
    When we execute query on clickhouse01
    """
    CREATE TABLE non_repl_db.foo
    ON CLUSTER '{cluster}'
    (
        `a` Int
    )
    ENGINE = MergeTree
    ORDER BY a
    """
    And we execute query on clickhouse01
    """
    INSERT INTO non_repl_db.foo VALUES (42)
    """
    And we execute query on clickhouse02
    """
    INSERT INTO non_repl_db.foo VALUES (42)
    """
    And we execute command on clickhouse01
    """
    chadmin database migrate -d non_repl_db 
    """
    When we execute query on clickhouse02
    """
    ALTER TABLE non_repl_db.foo ADD COLUMN b String DEFAULT 'value'
    """

    When we execute command on clickhouse02
    """
    chadmin zookeeper list /clickhouse/non_repl_db/replicas
    """
    Then we get response contains
    """
    /clickhouse/non_repl_db/replicas/shard1|clickhouse01.ch_tools_test
    """

    When we try to execute command on clickhouse02
    """
    chadmin database migrate -d non_repl_db 
    """
    Then it fails with response contains
    """
    Local table metadata for table foo is different from zk metadata
    """
    When we execute query on clickhouse01
    """
    SELECT * FROM non_repl_db.foo FORMAT Values
    """
    Then we get response
    """
    (42)
    """
    When we execute query on clickhouse02
    """
    SELECT * FROM non_repl_db.foo FORMAT Values
    """
    Then we get response
    """
    (42,'value')
    """

    When we execute query on clickhouse01
    """
    ALTER TABLE non_repl_db.foo ADD COLUMN b String DEFAULT 'value'
    """
    When we execute command on clickhouse02
    """
    chadmin database migrate -d non_repl_db 
    """

    When we execute command on clickhouse02
    """
    supervisorctl restart clickhouse-server
    """
    When we sleep for 10 seconds
    When we execute query on clickhouse01
    """
    SELECT * FROM non_repl_db.foo FORMAT Values
    """
    Then we get response
    """
    (42,'value')
    """
    When we execute query on clickhouse02
    """
    SELECT * FROM non_repl_db.foo FORMAT Values
    """
    Then we get response
    """
    (42,'value')
    """
